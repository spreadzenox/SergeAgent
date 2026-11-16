#!/usr/bin/env python3
"""L'essai total (lot 12, décision Q99) : un seul essai, de bout en bout.

Seuls le canal e-mail, le pont téléphonique (sa réponse à « composer ») et
les modèles sont des faux ; le pipeline en base, l'interpréteur, les
garde-fous et le journal des appels sont réels. Les coordonnées sont
fausses : les vraies ne sont tapées que dans Mission Control. Les étapes 2
et 5 (construire, publier, payer) sont essayées dans test_bout_en_bout et
test_etape5 ; ici, leurs tâches attendent.

Scénarios :
- à partir de l'étape 3 : le business d'essai « Calculatrice », la fiche
  de la personne avec son accord « test », un e-mail envoyé et un appel
  composé, même un dimanche ; les deux campagnes se terminent aussitôt,
  le test est mesuré et retenu quoi qu'il arrive, le ticket « Choix du
  principal » arrive, marqué « essai » ; validé, le produit fini part en
  conception ;
- l'essai ne touche à rien de vrai : avec trois vrais business en test, un
  vrai cycle ouvert et un vrai principal, aucune vraie ligne ne change et
  aucune vraie tâche n'est créée ;
- à partir de l'étape 1 : un cycle d'écoute d'essai, 2 recherches et 5
  pages au plus, marquées ; « Choisir les business » ne voit que la
  calculatrice ; son plan tout fait part au ticket « Plan » ;
- à partir de l'étape 6 : la prospection lourde écrit et appelle le
  contact de l'essai, lui seul ;
- relancer l'essai arrête le précédent et le remplace ;
- la case « Valider chaque brouillon » : l'e-mail et l'appel attendent un
  humain ;
- un numéro français tapé tel quel (06…) est mis au format +33 ; un numéro
  illisible arrête l'essai avec la raison, rien ne part ; un essai relancé
  après un « STOP » lève la désinscription de ces adresses-là ;
- le dernier essai est visible dans Mission Control (page Système).
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.canaux import ensure_canaux  # noqa: E402
from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.base import Adapter, Outgoing  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.store import default_canon_path, open_db  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.rules import quota_usage  # noqa: E402
from serge.interpreter.triggers import fire_button  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.privacy import subject_hash  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402
from serge.trial import active_run  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import default_ledger_path  # noqa: E402

DIMANCHE = '2026-09-06T10:30:00+00:00'
DEPART = 'étape de départ (1, 2, 3, 5 ou 6)'
FORMULAIRE = {
    'nom': 'Essai Testeur',
    'e-mail': 'essai@exemple.fr',
    'téléphone (+33…)': '+33600000001',
    DEPART: '3',
}
BUT = 'Présenter la calculatrice et obtenir un rendez-vous.'


class FauxModeles:
    """Les modèles de l'essai, reconnus à leur consigne."""

    def __init__(self) -> None:
        self.recu: dict[str, list[str]] = {}

    def __call__(self, _key, _model, messages, tools=None, **_kw):
        system, user = messages[0]['content'], messages[1]['content']
        for marque, role in (
            ('Tu écris le premier e-mail', 'email'),
            ('Tu prépares le premier appel', 'appel'),
            ('Tu fais le bilan', 'bilan'),
            ('Tu proposes le business principal', 'principal'),
            ('est en vente. Tu prépares', 'lourde'),
            ('Tu cherches sur le web des besoins', 'explorer'),
            ('Tu tries des pages web', 'trier'),
            ('Tu formules des idées de business', 'formuler'),
            ('Tu choisis les business', 'choisir'),
        ):
            if marque in system:
                self.recu.setdefault(role, []).append(f'{system}\n{user}')
                return ChatResult(
                    json.dumps(self._reponse(role, user)), 10, 10, 'faux', 1
                )
        raise AssertionError(f'consigne inattendue : {system[:90]}')

    @staticmethod
    def _reponse(role: str, user: str) -> dict[str, Any]:
        numeros = re.findall(r'"id": "(ven_[0-9a-f]+)"', user)
        return {
            'email': {
                'subject': 'Une calculatrice en ligne',
                'body': 'Bonjour, essayez notre calculatrice.',
            },
            'appel': {'body': BUT},
            'bilan': {'bilan': 'Personne n’a encore répondu.'},
            'principal': {
                'business': numeros[0] if numeros else '',
                'notes': 'La calculatrice est la seule.',
            },
            'lourde': {
                'campagnes': [
                    {'canal': c, 'cible': 'Tout le monde.', 'angle': 'Simple.'}
                    for c in ('email', 'voice')
                ],
                'compte_rendu': 'Deux campagnes.',
            },
            'explorer': {
                'pages': [
                    {
                        'url': 'https://forum.exemple.fr/calcul',
                        'titre': 'Je cherche une calculatrice simple',
                        'apercu': 'Les calculatrices en ligne sont pleines de pub.',
                    }
                ]
            },
            'trier': {'besoin_nouveau': [], 'bruit': [], 'enrichit': []},
            'formuler': {'fiches': []},
            'choisir': {
                'choix': [
                    {'business': n, 'raison': 'Seul candidat.'}
                    for n in numeros[:1]
                ],
                'note': '',
            },
        }[role]


class EssaiTotalTests(unittest.TestCase):
    def setUp(self) -> None:
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        root = Path(dossier.name)
        instance = root / 'instance.toml'
        instance.write_text('[features]\nphone_voice = true\n')
        patcher = mock.patch.dict(
            os.environ,
            {
                'SERGE_SYSTEM_ROOT': str(root),
                'SERGE_INSTANCE_FILE': str(instance),
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = open_db(default_canon_path())
        self.addCleanup(self.conn.close)
        self.ledger = VoiceLedger(default_ledger_path())
        self.mails: list[Outgoing] = []
        self.composes: list[dict[str, Any]] = []
        faux_mail = Adapter(
            'email',
            'E-mail',
            '',
            'email',
            'x.py',
            lambda m: self.mails.append(m) or f'<{m.touch_id}@serge>',
            lambda _m: '',
        )
        for patcher in (
            mock.patch.dict(ADAPTERS, {'email': faux_mail}),
            mock.patch('serge.channels.voice._bridge', side_effect=self._pont),
            mock.patch(
                'serge.voice.bridge.originate', side_effect=self._composer
            ),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        ensure_canaux(self.conn)
        # Rien d'autre ne tourne : ni relève, ni relances. Construire et
        # publier (étapes 2 et 5) ont leurs propres scénarios.
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        self.conn.execute(
            "UPDATE pipeline_steps SET enabled=0 WHERE id='build_venture'"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()
        self.modeles = FauxModeles()

    def _pont(
        self, path: str, payload: dict[str, str] | None = None
    ) -> dict[str, Any]:
        from serge.voice.bridge import originate_for_task

        if path.startswith('/calls'):
            return {'calls': []}
        return originate_for_task(dict(payload or {}))

    def _composer(self, **demande: Any) -> dict[str, Any]:
        self.composes.append(demande)
        return {
            'decision': 'allowed',
            'originated': True,
            'cdr_id': f'cdr_{len(self.composes)}',
        }

    def _un(self, sql: str, params: tuple = ()) -> tuple:
        return tuple(self.conn.execute(sql, params).fetchone())

    def _vider(self) -> None:
        # Un dimanche : l'appel d'essai part quand même (accord « test »).
        with mock.patch('serge.guards.check.utcnow', return_value=DIMANCHE):
            for _ in range(300):
                fait = [
                    process_one(self.conn, file, caller=self.modeles)
                    for file in ('works', 'conversations')
                ]
                if not any(fait):
                    return
        raise AssertionError('les files ne se vident pas')

    def _essai(self, formulaire: dict[str, str]) -> str:
        essai = fire_button(self.conn, 'bouton_essai_total', formulaire)
        assert essai is not None
        self.conn.commit()
        self._vider()
        return essai

    def _echecs(self) -> list[tuple]:
        return [
            tuple(e)
            for e in self.conn.execute(
                'SELECT invocation_id, last_error FROM tasks'
                " WHERE status='failed'"
            )
        ]

    def _repondre(self, sorte: str, acte: str) -> None:
        (ticket,) = self._un(
            "SELECT id FROM tickets WHERE type=? AND state='OPEN'"
            ' ORDER BY rowid DESC',
            (sorte,),
        )
        noter_reponse(self.conn, ticket, acte, '', 'owner')
        self.conn.commit()
        self._vider()

    def test_a_partir_de_l_etape_3_un_e_mail_un_appel_et_la_suite(
        self,
    ) -> None:
        essai = self._essai(FORMULAIRE)
        self.assertEqual(self._echecs(), [])
        self.assertEqual(active_run(self.conn), essai)
        venture, nom, marque = self._un('SELECT id, name, trial FROM ventures')
        self.assertEqual((nom, marque), ('Calculatrice', 1))
        contact, etape = self._un(
            "SELECT id, funnel_state FROM contacts WHERE display='Essai Testeur'"
        )
        self.assertEqual(etape, 'CONTACTING')
        self.assertEqual(
            self._un(
                "SELECT basis FROM consents WHERE channel='voice'"
                ' AND subject_hash=?',
                (subject_hash('+33600000001'),),
            ),
            ('test',),
        )
        # Un e-mail et un appel, à la personne de l'essai, et rien d'autre.
        self.assertEqual(
            [(m.address, m.subject) for m in self.mails],
            [('essai@exemple.fr', 'Une calculatrice en ligne')],
        )
        self.assertEqual(
            [(c['to_e164'], c['message']) for c in self.composes],
            [('+33600000001', BUT)],
        )
        envois = self.conn.execute(
            'SELECT channel, status FROM touches WHERE contact_id=?'
            ' ORDER BY channel',
            (contact,),
        ).fetchall()
        self.assertEqual(
            [tuple(e) for e in envois], [('email', 'sent'), ('voice', 'sent')]
        )
        # Le modèle a lu la fiche produit pour écrire.
        self.assertIn(
            'Pas de fonctions scientifiques', self.modeles.recu['email'][0]
        )
        # Les deux campagnes sont closes aussitôt, le test mesuré et retenu
        # quoi qu'il arrive (0 point), le principal proposé.
        self.assertEqual(
            [
                tuple(c)
                for c in self.conn.execute(
                    'SELECT channel, state, n_target FROM campaigns'
                    ' ORDER BY channel'
                )
            ],
            [('email', 'FINISHED', 1), ('voice', 'FINISHED', 1)],
        )
        self.assertEqual(
            self._un('SELECT contacted, points, verdict FROM test_reports'),
            (2, 0.0, 'retenu'),
        )
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures')[0], 'SMOKE_DONE'
        )
        self.assertEqual(
            self._un(
                "SELECT trial, state FROM tickets WHERE type='CHOIX_PRINCIPAL'"
            ),
            (1, 'OPEN'),
        )
        # Validé : la calculatrice entre en construction de son produit.
        self._repondre('CHOIX_PRINCIPAL', 'valider')
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures')[0], 'PRODUCT_BUILDING'
        )
        self.assertEqual(
            self._un(
                'SELECT status, trial_run FROM tasks'
                " WHERE invocation_id='concevoir_produit'"
            ),
            ('ready', essai),
        )
        # Toutes ses tâches sont de l'essai ; aucune leçon, aucun cycle.
        self.assertEqual(
            self._un("SELECT COUNT(*) FROM tasks WHERE trial_run=''"), (0,)
        )
        self.assertEqual(self._un('SELECT COUNT(*) FROM listen_cycles'), (0,))

    def test_l_essai_ne_touche_a_rien_de_vrai(self) -> None:
        self.conn.executescript(
            """
            INSERT INTO ventures(id, name, description, lifecycle,
                created_at, updated_at)
            VALUES('v1', 'Devis', 'Des devis.', 'POC_SELECTED', 't', 't'),
                ('v2', 'Paie', 'La paie.', 'SMOKE_READY', 't', 't'),
                ('v3', 'Stock', 'Le stock.', 'SMOKE_DONE', 't', 't'),
                ('v4', 'Calculette', 'Une calculatrice en ligne, simple.',
                    'PRODUCT_BUILDING', 't', 't');
            INSERT INTO listen_cycles(id, status, created_at)
            VALUES('c1', 'OPEN', 't');
            """
        )
        self.conn.commit()

        def vrai() -> dict[str, Any]:
            return {
                'business': [
                    tuple(r)
                    for r in self.conn.execute(
                        'SELECT id, lifecycle, updated_at FROM ventures'
                        ' WHERE trial=0 ORDER BY id'
                    )
                ],
                'cycles': [
                    tuple(r)
                    for r in self.conn.execute(
                        'SELECT id, status FROM listen_cycles WHERE trial=0'
                    )
                ],
                'taches': self._un(
                    "SELECT COUNT(*) FROM tasks WHERE trial_run=''"
                ),
                'tickets': self._un(
                    'SELECT COUNT(*) FROM tickets WHERE trial=0'
                ),
                'places': [
                    quota_usage(self.conn, q)[:2]
                    for q in (
                        'places_de_test',
                        'place_lourde',
                        'cycles_ouverts',
                    )
                ],
            }

        avant = vrai()
        self.assertEqual(avant['places'], [(3, 3), (1, 1), (1, 1)])
        # Les places sont prises et un vrai cycle est ouvert : l'essai
        # écoute quand même le web et choisit sa calculatrice.
        self._essai({**FORMULAIRE, DEPART: '1'})
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un('SELECT COUNT(*), MAX(trial) FROM listen_cycles'), (2, 1)
        )
        self.assertEqual(vrai(), avant)
        # Un second essai, du test léger au principal : la place lourde,
        # prise par un vrai business, ne l'arrête pas.
        self._essai(FORMULAIRE)
        self._repondre('CHOIX_PRINCIPAL', 'valider')
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un(
                'SELECT lifecycle FROM ventures WHERE trial=1'
                ' ORDER BY rowid DESC'
            )[0],
            'PRODUCT_BUILDING',
        )
        self.assertEqual(vrai(), avant)
        # Les vraies invocations ne voient pas l'essai : « Choisir les
        # business » n'a vu que la calculatrice, pas les vrais en test.
        self.assertNotIn('Devis', self.modeles.recu['choisir'][0])
        self.assertIn('Calculatrice', self.modeles.recu['choisir'][0])

    def test_a_partir_de_l_etape_1_l_ecoute_est_petite_et_marquee(
        self,
    ) -> None:
        self._essai({**FORMULAIRE, DEPART: ''})
        self.assertEqual(self._echecs(), [])
        # Un cycle d'essai, fermé par « Choisir les business ».
        self.assertEqual(
            self._un('SELECT trial, status FROM listen_cycles'), (1, 'CLOSED')
        )
        consigne = self.modeles.recu['explorer'][0]
        self.assertIn('au plus 2 recherches', consigne)
        self.assertIn('au plus 5 pages', consigne)
        self.assertEqual(
            self._un('SELECT url, trial FROM listen_docs'),
            ('https://forum.exemple.fr/calcul', 1),
        )
        # La calculatrice est choisie, son plan tout fait attend Julien.
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures')[0], 'POC_SELECTED'
        )
        self.assertEqual(
            self._un("SELECT trial, state FROM tickets WHERE type='PLAN_POC'"),
            (1, 'OPEN'),
        )
        self.assertEqual(
            [
                tuple(c)
                for c in self.conn.execute(
                    'SELECT channel, state FROM campaigns ORDER BY channel'
                )
            ],
            [('email', 'DRAFT'), ('voice', 'DRAFT')],
        )
        self.assertNotIn('concevoir', self.modeles.recu)

    def test_a_partir_de_l_etape_6_la_prospection_lourde(self) -> None:
        self._essai({**FORMULAIRE, DEPART: '6'})
        self.assertEqual(self._echecs(), [])
        self.assertEqual(
            self._un('SELECT lifecycle FROM ventures')[0], 'FULL_RUNNING'
        )
        self.assertEqual(
            [
                tuple(c)
                for c in self.conn.execute(
                    'SELECT phase, channel, state FROM campaigns'
                    ' ORDER BY channel'
                )
            ],
            [('full', 'email', 'FINISHED'), ('full', 'voice', 'FINISHED')],
        )
        self.assertEqual([m.address for m in self.mails], ['essai@exemple.fr'])
        self.assertEqual(
            [c['to_e164'] for c in self.composes], ['+33600000001']
        )
        self.assertEqual(
            self._un("SELECT title, trial FROM tickets WHERE type='FYI'"),
            ("La prospection lourde d'un business est lancée", 1),
        )

    def test_relancer_l_essai_remplace_le_precedent(self) -> None:
        premier = self._essai(FORMULAIRE)
        second = self._essai(FORMULAIRE)
        self.assertNotEqual(premier, second)
        self.assertEqual(active_run(self.conn), second)
        self.assertEqual(
            [
                str(r[0])
                for r in self.conn.execute(
                    'SELECT lifecycle FROM ventures ORDER BY rowid'
                )
            ],
            ['KILLED', 'SMOKE_DONE'],
        )
        # Le ticket du premier essai est fermé ; celui du second attend.
        self.assertEqual(
            [
                str(r[0])
                for r in self.conn.execute(
                    "SELECT state FROM tickets WHERE type='CHOIX_PRINCIPAL'"
                    ' ORDER BY rowid'
                )
            ],
            ['CANCELLED', 'OPEN'],
        )
        self.assertEqual(len(self.mails), 2)

    def test_la_case_valider_fait_attendre_le_premier_message(self) -> None:
        self._essai({**FORMULAIRE, 'Valider chaque brouillon': '1'})
        self.assertEqual(
            self._un('SELECT validate_drafts FROM ventures'), (1,)
        )
        self.assertEqual(self.mails, [])
        self.assertEqual(self.composes, [])
        envois = self.conn.execute(
            'SELECT channel, status FROM touches ORDER BY channel'
        ).fetchall()
        self.assertEqual(
            [tuple(e) for e in envois],
            [('email', 'waiting_owner'), ('voice', 'waiting_owner')],
        )
        self.assertEqual(
            self._un(
                'SELECT COUNT(*), MIN(trial) FROM tickets'
                " WHERE type='CONVERSATION' AND state='OPEN'"
            ),
            (2, 1),
        )

    def test_un_numero_national_est_mis_au_format_international(self) -> None:
        self._essai({**FORMULAIRE, 'téléphone (+33…)': '06 00 00 00 01'})
        self.assertEqual(
            [c['to_e164'] for c in self.composes], ['+33600000001']
        )

    def test_un_essai_relance_apres_stop_peut_reecrire(self) -> None:
        self.conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1', '*', ?, 'désinscription', 't')",
            (subject_hash('essai@exemple.fr'),),
        )
        self.conn.commit()
        self._essai(FORMULAIRE)
        self.assertEqual([m.address for m in self.mails], ['essai@exemple.fr'])
        self.assertEqual(self._un('SELECT COUNT(*) FROM blocklist'), (0,))

    def test_le_dernier_essai_est_dans_mission_control(self) -> None:
        from serge.mc.proj_systeme import project_essais

        self._essai(FORMULAIRE)
        vue = project_essais(self.conn, {}, '')
        self.assertEqual(
            [b['titre'] for b in vue['boutons']], ["Lancer l'essai total"]
        )
        essai = vue['essai']
        self.assertTrue(essai['en_cours'])
        self.assertEqual(essai['depart'], '3')
        self.assertEqual(essai['business']['nom'], 'Calculatrice')
        self.assertEqual(essai['contact'], 'Essai Testeur')
        self.assertEqual(
            sorted((e['sens'], e['canal'], e['statut']) for e in essai['fil']),
            [('envoi', 'email', 'sent'), ('envoi', 'voice', 'sent')],
        )
        self.assertEqual(
            [t['titre'] for t in essai['tickets']],
            ['Le choix du business principal attend ton avis'],
        )
        titres = [t['titre'] for t in essai['taches']]
        for titre in (
            "Lancer l'essai total",
            'Démarrer une campagne',
            'Écrire le premier e-mail',
            'Mesurer le test',
            'Choisir le business principal',
        ):
            self.assertIn(titre, titres)

    def test_un_numero_mal_forme_arrete_l_essai(self) -> None:
        self._essai({**FORMULAIRE, 'téléphone (+33…)': '12 34'})
        (erreur,) = self._un(
            "SELECT last_error FROM tasks WHERE status='failed'"
            " AND invocation_id='creer_contact_essai_total'"
        )
        self.assertIn('format international', erreur)
        self.assertEqual(self.mails, [])
        self.assertEqual(self.composes, [])


if __name__ == '__main__':
    unittest.main()
