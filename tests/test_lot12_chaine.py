#!/usr/bin/env python3
"""Le lot 12, du POC en ligne à la vente : les étapes 3, 4 et 6.

La base, l'interpréteur et le pipeline de départ sont réels. Les modèles
rendent des réponses écrites à l'avance, les canaux sont des faux qui
gardent ce qui part, et la question DNS d'« Ajouter un prospect » ne sort
pas. Les déclencheurs horaires sont éteints : le test lance « Suivre une
campagne » lui-même, après avoir vieilli les envois.

Scénarios :
- un POC est en ligne : sa campagne démarre, Serge trouve deux prospects
  (une adresse générique et un domaine sans e-mail sont refusés), leur
  écrit ; huit jours sans envoi, la campagne se clôt, le test est mesuré,
  retenu, son bilan écrit ; le principal est proposé, Julien valide, le
  produit fini part en conception ; le produit en vente, la prospection
  lourde démarre, l'intéressé du test est prévenu ; un paiement arrive,
  son contact devient client ;
- un test sous les seuils : le business est arrêté, donne une leçon, et
  sa place relance un cycle d'écoute ;
- un canal de plus se branche sans toucher au reste : son adaptateur, son
  réglage de volume, son invocation de premier message et son lien ;
- une campagne par téléphone ne démarre pas pour des inconnus : le canal
  demande leur accord ; sans cet accord demandé (page Policy), elle
  démarre.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.campaigns import prospect  # noqa: E402
from serge.canaux import ensure_canaux  # noqa: E402
from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.channels.base import Adapter, Incoming, Outgoing  # noqa: E402
from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.interpreter.triggers import notify_rows_written  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.tickets import decide  # noqa: E402
from serge.tickets.reponses import noter_reponse  # noqa: E402

T = '2026-11-01T09:00:00+00:00'


class FauxCanal:
    """Un canal qui garde ce qui part, et rend ce qu'on lui fait recevoir."""

    def __init__(self) -> None:
        self.partis: list[Outgoing] = []
        self.recus: list[Incoming] = []

    def send(self, message: Outgoing) -> str:
        self.partis.append(message)
        return f'<{message.touch_id}@faux>'

    def confirm(self, _message: Outgoing) -> str:
        return ''

    def poll(self, _since: str, _boxes: tuple = ()) -> list[Incoming]:
        recus, self.recus = self.recus, []
        return recus


def _adaptateur(ident: str, sorte: str, canal: FauxCanal) -> Adapter:
    return Adapter(
        ident,
        ident,
        'Faux canal.',
        sorte,
        'tests/test_lot12_chaine.py',
        canal.send,
        canal.confirm,
        canal.poll,
    )


def _ajout(n: int, **champs: str) -> ToolCall:
    return ToolCall(f'a{n}', 'ajouter_prospect', json.dumps(champs))


PROSPECTS = [
    {
        'name': 'Accueil',
        'company': 'Plomberie Durand',
        'address': 'contact@durand-plomberie.fr',
        'source_url': 'https://durand-plomberie.fr/contact',
    },
    {
        'name': 'Luc Fantôme',
        'address': 'luc@domaine-invente.fr',
        'source_url': 'https://annuaire.exemple.fr/luc',
    },
    {
        'name': 'Marie Dupont',
        'company': 'Dupont Bâtiment',
        'role': 'gérante',
        'why': 'Fait ses devis à la main.',
        'address': 'Marie.Dupont@dupont-batiment.fr',
        'source_url': 'https://dupont-batiment.fr/equipe',
    },
    {
        'name': 'Paul Martin',
        'company': 'Martin Élec',
        'role': 'artisan',
        'address': 'paul@martin-elec.fr',
        'source_url': 'https://martin-elec.fr/mentions-legales',
    },
]


class FauxModeles:
    """Les modèles du lot 12, reconnus à la première phrase de leur
    consigne."""

    def __init__(self, prospects: list[dict[str, str]]) -> None:
        self.prospects = list(prospects)
        self.vus: list[str] = []
        self.refus: list[str] = []
        self.propose = 'v1'

    def __call__(self, _key, model, messages, tools=None, **_kw):
        system = messages[0]['content']
        outils = [m for m in messages if m.get('role') == 'tool']
        if 'Tu trouves des prospects' in system:
            self.vus.append('trouver')
            self.refus += [
                json.loads(m['content']).get('refus', '') for m in outils
            ][len(self.refus) :]
            if self.prospects and not outils:
                appels = tuple(
                    _ajout(n, **p) for n, p in enumerate(self.prospects)
                )
                self.prospects = []
                return ChatResult('', 10, 10, model, 1, tool_calls=appels)
            return self._json({'compte_rendu': 'Deux artisans trouvés.'})
        for marque, role, reponse in (
            (
                'Tu écris le premier e-mail',
                'email',
                {'subject': 'Vos devis', 'body': 'Bonjour, essayez le POC.'},
            ),
            ('Tu fais le bilan', 'bilan', {'bilan': 'Les artisans aiment.'}),
            (
                'Tu proposes le business principal',
                'principal',
                {'business': self.propose, 'notes': 'v1 : 8 points.'},
            ),
            (
                'est en vente. Tu prépares',
                'lourde',
                {
                    'campagnes': [
                        {
                            'canal': 'email',
                            'cible': 'Artisans du bâtiment, 1 à 5 salariés.',
                            'angle': 'Un devis en deux minutes.',
                        }
                    ],
                    'compte_rendu': 'Une campagne par e-mail.',
                },
            ),
            (
                "vient d'être arrêté",
                'lecon',
                {'lecons': [{'lecon': 'Deux prospects ne disent rien.'}]},
            ),
        ):
            if marque in system:
                self.vus.append(role)
                return self._json(reponse)
        raise AssertionError(f'consigne inattendue : {system[:90]}')

    @staticmethod
    def _json(data: dict[str, Any]) -> ChatResult:
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


def _dns(domaine: str, _resolver: Any = None) -> tuple[bool | None, str]:
    if 'invente' in domaine:
        return False, 'le domaine n’existe pas'
    return True, ''


class ChaineCase(unittest.TestCase):
    def setUp(self) -> None:
        self.email, self.voix, self.pigeon = (
            FauxCanal(),
            FauxCanal(),
            FauxCanal(),
        )
        for patcher in (
            mock.patch.dict(
                ADAPTERS,
                {
                    'email': _adaptateur('email', 'email', self.email),
                    'voice': _adaptateur('voice', 'phone', self.voix),
                },
            ),
            mock.patch.object(prospect, 'receives_mail', _dns),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event IN ('every', 'at')"
        )
        # Les étapes 1 et 5 ne tournent pas ici : leurs tâches attendent.
        self.conn.execute(
            'UPDATE pipeline_steps SET enabled=0 WHERE id IN'
            " ('pre_prospection', 'build_venture')"
        )
        self._regler('demarrer_campagne', 'email_test', 2)
        set_heartbeat(self.conn, True)
        self.modeles = FauxModeles(PROSPECTS)
        self.conn.commit()

    def _regler(self, invocation: str, nom: str, valeur: int) -> None:
        self.conn.execute(
            'UPDATE invocation_settings SET value=? WHERE invocation_id=?'
            ' AND name=?',
            (str(valeur), invocation, nom),
        )

    def _business(self, ident: str, canal: str = 'email') -> str:
        """Un business dont le POC vient d'être validé, avec son plan, sa
        fiche produit et sa campagne de test."""
        self.conn.executescript(
            f"""
            INSERT INTO ventures(id, name, description, lifecycle,
                created_at, updated_at)
            VALUES('{ident}', 'Devis {ident}', 'Des devis en ligne pour les
                artisans {ident}.', 'POC_SELECTED', '{T}', '{T}');
            INSERT INTO product_sheets(id, venture_id, summary, price,
                created_at, updated_at)
            VALUES('ps_{ident}', '{ident}', 'Des devis en deux minutes.',
                'Gratuit pendant le test.', '{T}', '{T}');
            INSERT INTO product_plans(id, venture_id, kind, status, target,
                duration_days, created_at, updated_at)
            VALUES('pl_{ident}', '{ident}', 'poc', 'validated',
                'Artisans du bâtiment.', 10, '{T}', '{T}');
            INSERT INTO campaigns(id, venture_id, phase, channel, state,
                created_at, updated_at)
            VALUES('c_{ident}', '{ident}', 'smoke', '{canal}', 'DRAFT',
                '{T}', '{T}');
            """
        )
        enqueue_task(self.conn, 'poc_pret', {'venture_id': ident})
        return f'c_{ident}'

    def _vider(self) -> None:
        for _ in range(200):
            fait = [
                process_one(self.conn, file, caller=self.modeles)
                for file in ('works', 'conversations')
            ]
            if not any(fait):
                return
        raise AssertionError('les files ne se vident pas')

    def _un(self, sql: str, *args: Any) -> Any:
        row = self.conn.execute(sql, args).fetchone()
        return tuple(row) if row is not None else None

    def _statut(self, ident: str) -> str:
        return self._un('SELECT lifecycle FROM ventures WHERE id=?', ident)[0]

    def _suivre(self, campagne: str, jours: int) -> None:
        """Les envois ont ``jours`` jours ; « Suivre une campagne » passe."""
        avant = (datetime.now(UTC) - timedelta(days=jours)).isoformat()
        self.conn.execute(
            "UPDATE touches SET sent_at=? WHERE status='sent'", (avant,)
        )
        enqueue_task(
            self.conn,
            'suivre_campagne',
            {'campaign_id': campagne},
            origin_ref=f'test:{jours}:{avant}',
        )
        self._vider()

    def _taches(self, invocation: str) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                'SELECT status FROM tasks WHERE invocation_id=?'
                ' ORDER BY created_at, id',
                (invocation,),
            )
        ]


class ChaineTests(ChaineCase):
    def test_du_poc_en_ligne_a_la_vente(self) -> None:
        campagne = self._business('v1')
        self._vider()
        # La campagne a démarré, pour 2 prospects et 10 jours.
        etat, cible, fin = self._un(
            'SELECT state, n_target, planned_end_at FROM campaigns WHERE id=?',
            campagne,
        )
        self.assertEqual((etat, cible), ('RUNNING', 2))
        self.assertTrue(fin)
        self.assertEqual(self._statut('v1'), 'SMOKE_RUNNING')
        # Deux refus dits au modèle, deux prospects acceptés et écrits.
        self.assertIn('adresse générique (contact@)', self.modeles.refus[0])
        self.assertIn('le domaine n’existe pas', self.modeles.refus[1])
        self.assertEqual(
            [
                tuple(r)
                for r in self.conn.execute(
                    'SELECT c.display, c.note, c.funnel_state, a.value,'
                    ' a.source_url FROM contacts c JOIN contact_addresses a'
                    ' ON a.contact_id=c.id ORDER BY c.display'
                )
            ],
            [
                (
                    'Marie Dupont, gérante (Dupont Bâtiment)',
                    'Fait ses devis à la main.',
                    'CONTACTING',
                    'marie.dupont@dupont-batiment.fr',
                    'https://dupont-batiment.fr/equipe',
                ),
                (
                    'Paul Martin, artisan (Martin Élec)',
                    '',
                    'CONTACTING',
                    'paul@martin-elec.fr',
                    'https://martin-elec.fr/mentions-legales',
                ),
            ],
        )
        self.assertEqual(
            sorted(m.address for m in self.email.partis),
            ['marie.dupont@dupont-batiment.fr', 'paul@martin-elec.fr'],
        )
        # Un jour après : rien à faire. Marie répond « intéressé ».
        self._suivre(campagne, 1)
        self.assertEqual(self._un('SELECT state FROM campaigns')[0], 'RUNNING')
        marie = self._un(
            "SELECT id FROM contacts WHERE display LIKE 'Marie%'"
        )[0]
        self.conn.execute(
            'INSERT INTO inbound_events(id, contact_id, venture_id, channel,'
            ' native_type, address, body, status, reaction, signal,'
            " received_at) VALUES('in1', ?, 'v1', 'email', 'message',"
            " 'marie.dupont@dupont-batiment.fr', 'Ça m’intéresse.',"
            " 'attached', 'intéressé', '', ?)",
            (marie, T),
        )
        self.conn.execute(
            "UPDATE contacts SET funnel_state='INTENT' WHERE id=?", (marie,)
        )
        # Neuf jours sans envoi : la campagne se clôt, le test est mesuré.
        for nom, valeur in (('prospects_min', 2), ('points_min', 5)):
            self._regler('mesurer_test', nom, valeur)
        self._suivre(campagne, 9)
        self.assertEqual(
            self._un(
                'SELECT state, end_reason FROM campaigns WHERE id=?', campagne
            ),
            ('FINISHED', 'tous ses prospects sont contactés et relancés'),
        )
        contactes, reponses, points, verdict, bilan = self._un(
            'SELECT contacted, replies, points, verdict, summary'
            ' FROM test_reports'
        )
        self.assertEqual((contactes, reponses, verdict), (2, 1, 'retenu'))
        self.assertGreaterEqual(points, 5)
        self.assertEqual(bilan, 'Les artisans aiment.')
        # Le test est retenu ; le principal est proposé à Julien.
        ticket, etat_ticket = self._un(
            "SELECT id, state FROM tickets WHERE type='CHOIX_PRINCIPAL'"
        )
        self.assertEqual(etat_ticket, 'OPEN')
        self.assertEqual(self._statut('v1'), 'SMOKE_DONE')
        # Comme un clic sur « Valider » : le ticket est tranché, puis sa
        # réponse réveille « Appliquer le choix ».
        decide(self.conn, ticket, 'APPROVED')
        noter_reponse(self.conn, ticket, 'valider', '', 'owner')
        self._vider()
        self.assertEqual(self._statut('v1'), 'PRODUCT_BUILDING')
        self.assertEqual(
            self._un(
                'SELECT status, decision, chosen_venture_id FROM principal_choices'
            ),
            ('DECIDED', 'valider', 'v1'),
        )
        # Une réponse appliquée ne rouvre pas de ticket (essai total du 17
        # novembre 2026 : un second ticket arrivait après « Valider »).
        self.assertEqual(
            self._un(
                "SELECT COUNT(*) FROM tickets WHERE type='CHOIX_PRINCIPAL'"
            ),
            (1,),
        )
        # La conception du produit fini attend (l'étape 5 est éteinte ici).
        self.assertEqual(self._taches('concevoir_produit'), ['ready'])
        # Le produit est en vente : la prospection lourde démarre.
        self.conn.execute(
            "UPDATE ventures SET lifecycle='PRODUCT_READY' WHERE id='v1'"
        )
        self.modeles.prospects = [
            {
                'name': 'Zoé Petit',
                'address': 'zoe@petit-toiture.fr',
                'source_url': 'https://petit-toiture.fr/equipe',
            }
        ]
        notify_rows_written(self.conn, 'ventures', ['v1'])
        self._vider()
        self.assertEqual(self._statut('v1'), 'FULL_RUNNING')
        self.assertEqual(
            self._un(
                'SELECT state, n_target, n_week, target FROM campaigns'
                " WHERE phase='full'"
            ),
            ('RUNNING', 1000, 200, 'Artisans du bâtiment, 1 à 5 salariés.'),
        )
        # Marie, intéressée pendant le test, et Zoé reçoivent un message.
        self.assertEqual(
            sorted(m.address for m in self.email.partis[2:]),
            ['marie.dupont@dupont-batiment.fr', 'zoe@petit-toiture.fr'],
        )
        # Marie paie : elle devient cliente, et la première vente est dite.
        self.conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            ' intent_id, status, receipt_json, created_at, updated_at)'
            " VALUES('tx1', 'v1', 'invoice', 29, 'pi_1', 'paid', ?, ?, ?)",
            (
                json.dumps(
                    {
                        'receipt': {
                            'customer_email': 'Marie.Dupont@dupont-batiment.fr'
                        }
                    }
                ),
                T,
                T,
            ),
        )
        notify_rows_written(self.conn, 'transactions', ['tx1'])
        self._vider()
        self.assertEqual(
            self._un('SELECT funnel_state FROM contacts WHERE id=?', marie)[0],
            'CUSTOMER',
        )
        titres = [
            str(r[0])
            for r in self.conn.execute(
                "SELECT title FROM tickets WHERE type='FYI' ORDER BY created_at"
            )
        ]
        self.assertEqual(
            titres,
            [
                "La prospection lourde d'un business est lancée",
                "Première vente d'un business",
            ],
        )

    def test_choisir_un_autre_business_que_la_proposition(self) -> None:
        """Deux tests retenus, Serge propose le premier. « Choisir un
        autre » avec un nom qui ne désigne aucun business : rien ne change,
        le ticket est rouvert avec la raison. Avec le bon nom : ce business
        entre en construction, l'autre est mis de côté, et aucun ticket de
        plus n'est ouvert. Une réponse qui arrive après ne rouvre rien."""
        self.conn.executescript(
            f"""
            INSERT INTO ventures(id, name, description, lifecycle,
                created_at, updated_at)
            VALUES('v1', 'Devis v1', 'Des devis.', 'SMOKE_DONE', '{T}', '{T}'),
                ('v2', 'Factures v2', 'Des factures.', 'SMOKE_DONE',
                '{T}', '{T}');
            INSERT INTO principal_choices(id, proposed_venture_id, notes,
                status, created_at, updated_at)
            VALUES('pc1', 'v1', 'v1 : le meilleur test.', 'PROPOSED',
                '{T}', '{T}');
            """
        )
        enqueue_task(
            self.conn, 'demander_choix_principal', {'choice_id': 'pc1'}
        )
        self._vider()

        def tickets() -> list[str]:
            return [
                str(r[0])
                for r in self.conn.execute(
                    "SELECT id FROM tickets WHERE type='CHOIX_PRINCIPAL'"
                    ' ORDER BY created_at, rowid'
                )
            ]

        def repondre(ticket: str, acte: str, texte: str) -> None:
            """Comme un clic dans Mission Control : le ticket est tranché,
            puis sa réponse réveille « Appliquer le choix »."""
            decide(
                self.conn,
                ticket,
                'EDITED' if acte == 'choisir_autre' else 'APPROVED',
                note=texte,
            )
            noter_reponse(self.conn, ticket, acte, texte, 'owner')
            self._vider()

        (premier,) = tickets()
        repondre(premier, 'choisir_autre', 'Plomberie')
        self.assertEqual(
            (self._statut('v1'), self._statut('v2')),
            ('SMOKE_DONE', 'SMOKE_DONE'),
        )
        self.assertEqual(
            self._un('SELECT status FROM principal_choices'), ('PROPOSED',)
        )
        _, second = tickets()
        self.assertIn(
            '« Plomberie » ne désigne aucun business',
            self._un('SELECT payload_json FROM tickets WHERE id=?', second)[0],
        )
        repondre(second, 'choisir_autre', 'factures v2')
        self.assertEqual(
            (self._statut('v1'), self._statut('v2')),
            ('PARKED', 'PRODUCT_BUILDING'),
        )
        self.assertEqual(
            self._un(
                'SELECT status, decision, chosen_venture_id'
                ' FROM principal_choices'
            ),
            ('DECIDED', 'choisir_autre', 'v2'),
        )
        self.assertEqual(tickets(), [premier, second])
        # Une réponse de plus (le délai du premier ticket qui expire, par
        # exemple) : le choix n'attend plus rien ; rien ne change et aucun
        # ticket n'est ouvert.
        noter_reponse(self.conn, premier, 'valider', '', 'owner')
        self._vider()
        self.assertEqual(tickets(), [premier, second])
        self.assertEqual(
            (self._statut('v1'), self._statut('v2')),
            ('PARKED', 'PRODUCT_BUILDING'),
        )

    def test_un_test_sous_les_seuils_arrete_le_business(self) -> None:
        campagne = self._business('v1')
        self._vider()
        self._suivre(campagne, 9)
        # 0 point, sous les 10 demandés : arrêté, avec la raison.
        self.assertEqual(
            self._un('SELECT verdict, verdict_reason FROM test_reports'),
            (
                'non_retenu',
                '2 prospect(s) contacté(s), moins que les 30 demandés',
            ),
        )
        self.assertEqual(self._statut('v1'), 'KILLED')
        self.assertEqual(
            self._un('SELECT statement, status, created_by FROM lessons'),
            ('Deux prospects ne disent rien.', 'candidate', 'tirer_lecon'),
        )
        # Sa place libérée relance l'écoute ; aucun principal à choisir.
        self.assertEqual(self._taches('ouvrir_cycle'), ['ready'])
        self.assertEqual(self._taches('choisir_principal'), [])

    def test_le_telephone_ne_demarre_pas_pour_des_inconnus(self) -> None:
        campagne = self._business('v1', canal='voice')
        self._vider()
        etat, raison = self._un(
            'SELECT state, end_reason FROM campaigns WHERE id=?', campagne
        )
        self.assertEqual(etat, 'CANCELLED')
        self.assertIn('demande l’accord de la personne', raison)
        self.assertEqual(self.voix.partis, [])
        self.assertEqual(
            self._un("SELECT title FROM tickets WHERE type='FYI'")[0],
            "Une campagne n'a pas pu démarrer",
        )

    def test_un_plan_a_plusieurs_canaux_ouvre_une_campagne_par_canal(
        self,
    ) -> None:
        """Décision Q117 : le plan nomme « email, voice ». La campagne du
        plan garde l'e-mail, une campagne sœur s'ouvre pour le téléphone,
        chacune cherche ses prospects, et une même personne n'est
        contactée que sur un canal."""
        set_setting(
            self.conn, 'consent.opt_in_channels', ['sms', 'whatsapp'], 'test'
        )
        self._regler('demarrer_campagne', 'voice_test', 1)
        self.conn.execute(
            "UPDATE invocations SET enabled=0 WHERE id='premier_appel'"
        )
        self.modeles.prospects = []
        campagne = self._business('v1', canal='email, voice')
        self._vider()
        self.assertEqual(
            sorted(
                tuple(r)
                for r in self.conn.execute(
                    'SELECT channel, state, n_target FROM campaigns'
                    " WHERE venture_id='v1'"
                )
            ),
            [('email', 'RUNNING', 2), ('voice', 'RUNNING', 1)],
        )
        self.assertEqual(
            self._un('SELECT channel FROM campaigns WHERE id=?', campagne),
            ('email',),
        )
        self.assertEqual(self.modeles.vus.count('trouver'), 2)
        soeur = self._un(
            "SELECT id FROM campaigns WHERE venture_id='v1'"
            " AND channel='voice'"
        )[0]

        def ajouter(ou: str, nom: str, adresse: str) -> dict[str, Any]:
            return prospect.add_prospect(
                self.conn,
                'ajouter_prospect',
                {
                    'campaign_id': ou,
                    'name': nom,
                    'address': adresse,
                    'source_url': 'https://dupont-batiment.fr/equipe',
                },
                'trouver_prospects',
            )

        self.assertTrue(
            ajouter(
                campagne, 'Marie Dupont', 'marie.dupont@dupont-batiment.fr'
            )['ok']
        )
        # La même personne, trouvée par son téléphone : refusée.
        refus = ajouter(soeur, 'Mme DUPONT Marie', '+33612345678')
        self.assertFalse(refus['ok'])
        self.assertIn('sur un autre canal', refus['refus'])
        self.assertTrue(ajouter(soeur, 'Paul Martin', '+33612345679')['ok'])
        self.assertEqual(
            prospect.person_key('Maître Élodie DUPONT-Martin'),
            prospect.person_key('Dupont Martin Elodie'),
        )

    def test_sans_accord_demande_le_telephone_demarre(self) -> None:
        # Le téléphone retiré de « Accord des gens » (page Policy) : la
        # campagne démarre, et Serge cherche des numéros (décision Q100).
        set_setting(
            self.conn, 'consent.opt_in_channels', ['sms', 'whatsapp'], 'test'
        )
        self._regler('demarrer_campagne', 'voice_test', 1)
        self.modeles.prospects = [
            {
                'name': 'Marie Dupont',
                'address': '+33612345678',
                'source_url': 'https://dupont-batiment.fr/equipe',
            }
        ]
        self.conn.execute(
            "UPDATE invocations SET enabled=0 WHERE id='premier_appel'"
        )
        campagne = self._business('v1', canal='voice')
        self._vider()
        self.assertEqual(
            self._un(
                'SELECT state, n_target FROM campaigns WHERE id=?', campagne
            ),
            ('RUNNING', 1),
        )
        self.assertEqual(
            self._un('SELECT channel, address, status FROM touches'),
            ('voice', '+33612345678', 'to_write'),
        )


def _v(source: str, value: str = '') -> dict[str, str]:
    return {'source': source, 'value': value}


class CanalDePlusTests(ChaineCase):
    """Le contrat d'un canal (conception du lot 12, partie 17)."""

    def test_un_canal_de_plus_se_branche_sans_toucher_au_reste(self) -> None:
        avant = {
            table: self.conn.execute(
                f'SELECT * FROM {table} ORDER BY 1, 2'
            ).fetchall()
            for table in ('invocations', 'links', 'triggers', 'tools')
        }
        # 1. son adaptateur ; 2. son réglage de volume ; 3. son invocation
        # de premier message et son lien.
        patcher = mock.patch.dict(
            ADAPTERS,
            {'pigeon': _adaptateur('pigeon', 'colombier', self.pigeon)},
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        ensure_canaux(self.conn)
        self.conn.execute(
            'INSERT INTO invocation_settings(invocation_id, name, value)'
            " VALUES('demarrer_campagne', 'pigeon_test', '1')"
        )
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {
                        'id': 'premier_pigeon',
                        'type': 'capability',
                        'capability': 'echo',
                        'queue': 'conversations',
                        'writes': [
                            {
                                'table': 'touches',
                                'operation': 'update',
                                'key': {
                                    'column': 'id',
                                    'source': 'task',
                                    'value': 'touch_id',
                                },
                                'values': {
                                    'body': _v('fixed', 'Roucoule.'),
                                    'status': _v('fixed', 'pending'),
                                },
                            }
                        ],
                    }
                ],
                'links': [
                    {
                        'id': 'premier_message_par_pigeon',
                        'from': 'rediger_premier_message',
                        'to': 'premier_pigeon',
                        'condition': {'field': 'channel', 'value': 'pigeon'},
                        'params': {'touch_id': _v('task', 'touch_id')},
                    },
                    {
                        'id': 'premier_pigeon_vers_envoi',
                        'from': 'premier_pigeon',
                        'to': 'envoyer_message',
                        'params': {'touch_id': _v('task', 'touch_id')},
                    },
                ],
            },
        )
        for table, lignes in avant.items():
            self.assertEqual(
                [
                    r
                    for r in self.conn.execute(
                        f'SELECT * FROM {table} ORDER BY 1, 2'
                    )
                    if r in lignes
                ],
                lignes,
                f'{table} : rien de ce qui existait n’a changé',
            )
        # La chaîne : campagne, prospect, premier message, envoi, réponse.
        self.modeles.prospects = [
            {
                'name': 'Jean Colombe',
                'address': 'pigeonnier-12',
                'source_url': 'https://colombophilie.exemple.fr/jean',
            }
        ]
        campagne = self._business('v1', canal='pigeon')
        self._vider()
        self.assertEqual(
            [(m.channel, m.address, m.body) for m in self.pigeon.partis],
            [('pigeon', 'pigeonnier-12', 'Roucoule.')],
        )
        self.pigeon.recus = [
            Incoming('p1', 'pigeonnier-12', '', 'Bien reçu.', message_ref='p1')
        ]
        enqueue_task(self.conn, 'relever_messages', {'channel': 'pigeon'})
        self.conn.execute(
            "UPDATE invocations SET enabled=0 WHERE id='traiter_reponse'"
        )
        self._vider()
        self.assertEqual(
            self._un('SELECT channel, status, venture_id FROM inbound_events'),
            ('pigeon', 'attached', 'v1'),
        )
        # La campagne se clôt et le test est mesuré, comme pour tout canal.
        self._suivre(campagne, 9)
        self.assertEqual(
            self._un('SELECT contacted, figures FROM test_reports')[0], 1
        )
        self.assertIn(
            'pigeon : 1 contacté(s)',
            self._un('SELECT figures FROM test_reports')[0],
        )


if __name__ == '__main__':
    unittest.main()
