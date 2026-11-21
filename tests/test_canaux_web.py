#!/usr/bin/env python3
"""Les canaux qui passent par le navigateur (lot 13, décision Q104).

Le pipeline de départ, en base, avec de faux modèles ; aucun navigateur :
les deux missions du canal (envoyer, lire la messagerie) sont des
invocations LLM, et leur faux modèle rend ce qu'il aurait vu.

Scénarios :
- LinkedIn traverse la chaîne comme l'e-mail : campagne, prospect (un
  profil, vérifié), premier message, validation par un humain demandée par
  le canal, envoi confié à la mission, réponse relevée et rattachée au
  bon contact malgré une adresse écrite autrement, sans doublon ;
- un envoi attend, sans échouer, quand le compte sert à une autre tâche ;
  un message que le site refuse est en échec, avec la raison ;
- le réseau ne laisse pas encore écrire à la personne (décision Q110) : la
  mission lui demande le contact et rend « attente » ; l'envoi attend, les
  rappels s'espacent, et il part quand elle a accepté ; passé le délai
  réglé, il échoue. Une demande de contact compte dans le plafond du jour.
  Un message d'essai qui attend repart tout seul, un nombre de fois borné ;
- sans compte en service, le canal n'est pas branché : la campagne est
  annulée, et rien n'est relevé.
"""

from __future__ import annotations

import json
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.conversations.send import _day_full  # noqa: E402
from serge.db.store import utcnow  # noqa: E402
from serge.funnels.contacts import normalise_value  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from tests.test_lot12_chaine import (  # noqa: E402
    ChaineCase,
    FauxModeles,
)

ANA = 'https://www.linkedin.com/in/ana-roux'
FIL = 'https://www.linkedin.com/messaging/thread/42'
NOTE = 'Serge, un agent IA. Vos devis en deux minutes : on essaie ?'
DEMANDE = 'Demande de connexion envoyée à Ana Roux : elle doit l’accepter.'
ESSAI = 'texte du message (280 caractères au plus pour LinkedIn)'
A_QUI = (
    "à qui écrire : son pseudo sur ce réseau, ou l'adresse de son profil"
    " (LinkedIn : l'adresse)"
)


class ModelesDuReseau(FauxModeles):
    """Les modèles du lot 12, plus ceux des canaux du navigateur."""

    def __init__(self, prospects: list[dict[str, str]]) -> None:
        super().__init__(prospects)
        self.envois: list[dict[str, str]] = []
        self.envoi: dict[str, str] = {'envoye': 'oui', 'reference': FIL}
        self.recus: list[dict[str, str]] = []
        self.releves = 0

    def __call__(self, _key, model, messages, tools=None, **_kw):
        system = messages[0]['content']
        if 'Tu écris le premier message de Serge' in system:
            self.vus.append('reseau')
            return self._json({'body': NOTE})
        if 'Tu envoies un message de Serge' in system:
            entete = str(messages[1]['content']).split('\n\n')[0]
            self.envois.append(json.loads(entete.split('\n', 1)[1]))
            return self._json(self.envoi)
        if 'Tu relèves la messagerie' in system:
            self.releves += 1
            return self._json({'messages': self.recus, 'resume': 'Vu.'})
        return super().__call__(_key, model, messages, tools, **_kw)

    @staticmethod
    def _json(data: dict[str, Any]) -> ChatResult:
        return ChatResult(json.dumps(data), 10, 10, 'faux', 1)


class CanauxWebTests(ChaineCase):
    def setUp(self) -> None:
        super().setUp()
        self.modeles = ModelesDuReseau([])
        self._compte('active')
        self._regler('demarrer_campagne', 'linkedin_test', 1)
        self.conn.commit()

    def _compte(self, etat: str) -> None:
        self.conn.execute(
            'INSERT INTO web_accounts(id, url, login, status, created_at,'
            " updated_at) VALUES('linkedin', 'https://www.linkedin.com',"
            " 'serge-ia', ?, ?, ?) ON CONFLICT(id) DO UPDATE SET"
            ' status=excluded.status',
            (etat, utcnow(), utcnow()),
        )

    def _regler_canal(self, nom: str, valeur: Any) -> None:
        self.assertEqual(
            set_setting(self.conn, f'channels.linkedin.{nom}', valeur, 'test'),
            '',
        )

    def _envoi(self) -> tuple[Any, ...]:
        return self._un(
            'SELECT status, external_ref, last_error, address FROM touches'
        )

    def test_linkedin_traverse_la_chaine(self) -> None:
        self.modeles.prospects = [
            # Refusés : pas une adresse, puis un profil d'un autre site.
            {'name': 'Ana Roux', 'address': 'ana-roux', 'source_url': ANA},
            {
                'name': 'Ana Roux',
                'address': 'https://exemple.fr/ana-roux',
                'source_url': ANA,
            },
            {
                'name': 'Ana Roux',
                'company': 'Roux Bâtiment',
                'role': 'gérante',
                'address': ANA,
                'source_url': ANA,
            },
        ]
        campagne = self._business('v1', canal='linkedin')
        self._vider()
        self.assertEqual(
            [r for r in self.modeles.refus if r][:2],
            [
                'adresse d’un profil attendue : celle de la personne sur'
                ' linkedin.com (https://linkedin.com/…), pas « ana-roux »',
                'adresse d’un profil attendue : celle de la personne sur'
                ' linkedin.com (https://linkedin.com/…), pas'
                ' « https://exemple.fr/ana-roux »',
            ],
        )
        # Le canal demande qu'un humain valide chaque message : rien n'est
        # parti, et le ticket de la conversation est ouvert.
        statut, _, raison, adresse = self._envoi()
        self.assertEqual((statut, adresse), ('waiting_owner', ANA))
        self.assertIn('« linkedin » demande de valider', raison)
        self.assertEqual(self.modeles.envois, [])
        self.assertEqual(
            self._un(
                "SELECT type, state FROM tickets WHERE type='CONVERSATION'"
            ),
            ('CONVERSATION', 'OPEN'),
        )
        # Validé : l'envoi est confié à la mission, avec ce qu'il lui faut.
        touche = self._un('SELECT id FROM touches')[0]
        self.conn.execute(
            "UPDATE touches SET owner_ok_at=?, status='pending'", (utcnow(),)
        )
        enqueue_task(self.conn, 'envoyer_message', {'touch_id': touche})
        self._vider()
        self.assertEqual(self._envoi()[:2], ('sent', FIL))
        self.assertEqual(
            {
                k: v
                for k, v in self.modeles.envois[0].items()
                if k != 'task_id'
            },
            {
                'compte': 'linkedin',
                'canal': 'linkedin',
                'adresse': ANA,
                'message': NOTE,
                'sorte': 'first',
            },
        )
        # Sa réponse : relevée par la mission, rattachée au contact même
        # si le site écrit son adresse autrement ; une seconde relève ne la
        # compte pas deux fois.
        self.conn.execute(
            "UPDATE invocations SET enabled=0 WHERE id='traiter_reponse'"
        )
        self.modeles.recus = [
            {
                'de': 'https://linkedin.com/in/Ana-Roux/',
                'texte': 'Oui, montrez.',
            }
        ]
        for _ in range(2):
            enqueue_task(
                self.conn,
                'relever_messages',
                {'channel': 'linkedin'},
                origin_ref=f'test:{self.modeles.releves}',
            )
            self._vider()
        self.assertEqual(self.modeles.releves, 2)
        self.assertEqual(
            self.conn.execute(
                'SELECT channel, status, venture_id, body FROM inbound_events'
            ).fetchall()[0][:],
            ('linkedin', 'attached', 'v1', 'Oui, montrez.'),
        )
        self.assertEqual(self._un('SELECT COUNT(*) FROM inbound_events')[0], 1)
        self.assertTrue(
            self._un('SELECT polled_at FROM canaux WHERE id=?', 'linkedin')[0]
        )
        # La campagne se clôt et le test est mesuré, comme pour tout canal.
        self._suivre(campagne, 9)
        self.assertIn(
            'linkedin : 1 contacté(s)',
            self._un('SELECT figures FROM test_reports')[0],
        )

    def _un_envoi_pret(self) -> str:
        self._regler_canal('validate_messages', 'non')
        self.modeles.prospects = [
            {'name': 'Ana Roux', 'address': ANA, 'source_url': ANA}
        ]
        self._business('v1', canal='linkedin')
        return 'v1'

    def test_un_compte_pris_fait_attendre_l_envoi(self) -> None:
        self._un_envoi_pret()
        self.conn.execute(
            "UPDATE web_accounts SET used_by='t_autre', used_since=?",
            (utcnow(),),
        )
        self._vider()
        statut, _, raison, _ = self._envoi()
        self.assertEqual(
            (statut, raison), ('pending', 'le compte sert à une autre tâche')
        )
        self.assertEqual(self.modeles.envois, [])
        # L'envoi est remis à plus tard, dans dix minutes.
        self.assertTrue(
            self._un(
                "SELECT not_before FROM tasks WHERE invocation_id='envoyer_message'"
                " AND status='ready'"
            )[0]
        )

    def test_un_message_que_le_site_refuse(self) -> None:
        self._un_envoi_pret()
        self.modeles.envoi = {
            'envoye': 'non',
            'raison': 'LinkedIn ne permet plus de note ce mois-ci.',
        }
        self._vider()
        statut, _, raison, _ = self._envoi()
        self.assertEqual(
            (statut, raison),
            ('failed', 'LinkedIn ne permet plus de note ce mois-ci.'),
        )

    def _reprise(self, invocation: str = 'envoyer_message') -> datetime:
        """L'heure où la tâche en attente repartira."""
        quand = self._un(
            'SELECT not_before FROM tasks WHERE invocation_id=?'
            " AND status='ready'",
            invocation,
        )
        assert quand is not None and quand[0], invocation
        return datetime.fromisoformat(quand[0])

    def _le_temps_passe(
        self, jours: float = 0, invocation: str = 'envoyer_message'
    ) -> None:
        """La tâche en attente est due ; le contact a été demandé il y a
        ``jours`` jours."""
        if jours:
            self.conn.execute(
                'UPDATE touches SET contact_asked_at=?',
                ((datetime.now(UTC) - timedelta(days=jours)).isoformat(),),
            )
        self.conn.execute(
            "UPDATE tasks SET not_before='' WHERE invocation_id=?"
            " AND status='ready'",
            (invocation,),
        )
        self._vider()

    def _dans(self, quand: datetime) -> float:
        """Dans combien d'heures, à une minute près."""
        return round((quand - datetime.now(UTC)).total_seconds() / 3600, 1)

    def test_le_contact_demande_fait_attendre_l_envoi(self) -> None:
        """Ana n'est pas une relation et LinkedIn refuse la note : Serge
        lui demande la connexion, l'envoi attend, et il part quand elle a
        accepté."""
        self._un_envoi_pret()
        self.modeles.envoi = {'envoye': 'attente', 'raison': DEMANDE}
        self._vider()
        statut, ref, raison, _ = self._envoi()
        self.assertEqual((statut, ref, raison), ('pending', '', DEMANDE))
        demande = self._un('SELECT contact_asked_at FROM touches')[0]
        self.assertTrue(demande)
        # Premier rappel dans 12 heures (page Policy, « Comptes web »).
        self.assertEqual(self._dans(self._reprise()), 12.0)
        self.assertEqual(len(self.modeles.envois), 1)
        # Mission Control le dit sur la fiche de l'envoi.
        touche = self._un('SELECT id FROM touches')[0]
        fiche = project_objet(self.conn, 'touch', touche)
        assert fiche is not None
        self.assertEqual(
            [(c['k'], c['v']) for c in fiche['champs'][3:]],
            [('Raison', DEMANDE), ('Contact demandé', demande)],
        )
        # Ana a accepté : au rappel, le même texte part.
        self.modeles.envoi = {'envoye': 'oui', 'reference': FIL}
        self._le_temps_passe()
        self.assertEqual(self._envoi()[:2], ('sent', FIL))
        self.assertEqual(
            [e['message'] for e in self.modeles.envois], [NOTE, NOTE]
        )
        # L'heure de la demande reste sur l'envoi.
        self.assertEqual(
            self._un('SELECT contact_asked_at FROM touches')[0], demande
        )

    def test_les_rappels_s_espacent_puis_l_envoi_echoue(self) -> None:
        """Chaque attente dure autant que tout ce qui a déjà été attendu ;
        au bout du délai réglé, Serge regarde une dernière fois, puis
        l'envoi échoue avec sa raison."""
        self._un_envoi_pret()
        self.modeles.envoi = {'envoye': 'attente'}
        self._vider()
        # Sans raison rendue par la mission, l'envoi dit quand même
        # pourquoi il attend.
        self.assertEqual(
            self._envoi()[2],
            'contact demandé : le message partira quand la personne'
            ' l’aura accepté',
        )
        self._le_temps_passe(jours=3)
        self.assertEqual(self._dans(self._reprise()), 72.0)
        # À 13 jours et demi, le dernier rappel tombe au quatorzième jour.
        self._le_temps_passe(jours=13.5)
        self.assertEqual(self._dans(self._reprise()), 12.0)
        self._le_temps_passe(jours=14.1)
        statut, _, raison, _ = self._envoi()
        self.assertEqual(
            (statut, raison),
            (
                'failed',
                'la personne n’a pas accepté le contact en 14 jours : le'
                ' message n’est pas parti',
            ),
        )
        self.assertEqual(len(self.modeles.envois), 4)
        self.assertIsNone(
            self._un(
                "SELECT 1 FROM tasks WHERE invocation_id='envoyer_message'"
                " AND status='ready'"
            )
        )

    def test_une_demande_de_contact_compte_dans_le_plafond(self) -> None:
        """Dix demandes de connexion dans la journée valent dix messages :
        le plafond du jour du canal les compte, sauf celle de l'envoi qui
        repart."""
        self._un_envoi_pret()
        self._regler_canal('max_per_day', 1)
        self.modeles.envoi = {'envoye': 'attente', 'raison': DEMANDE}
        self._vider()
        touche = self._un('SELECT id FROM touches')[0]
        self.assertTrue(_day_full(self.conn, 'linkedin', 'un_autre_envoi'))
        self.assertEqual(_day_full(self.conn, 'linkedin', touche), '')
        # Demandé hier, il ne prend plus rien au plafond d'aujourd'hui.
        self.conn.execute(
            'UPDATE touches SET contact_asked_at=?',
            ((datetime.now(UTC) - timedelta(days=1)).isoformat(),),
        )
        self.assertEqual(
            _day_full(self.conn, 'linkedin', 'un_autre_envoi'), ''
        )

    def _essai(self, texte: str) -> None:
        from serge.interpreter.triggers import fire_button

        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_message_d_essai_reseau',
                {
                    'nom du compte (linkedin, instagram, x…)': 'linkedin',
                    A_QUI: 'ana_roux',
                    ESSAI: texte,
                },
            )
        )
        self.conn.commit()
        self._vider()

    def _essais(self) -> list[tuple[str, str, str]]:
        """Les passages d'un message d'essai : son état, ce qu'il a rendu,
        et son numéro de rappel."""
        return [
            (
                str(statut),
                str(json.loads(reponse or '{}').get('envoye') or ''),
                str(rappel or ''),
            )
            for statut, reponse, rappel in self.conn.execute(
                'SELECT t.status, t.answer_json, p.value FROM tasks t'
                ' LEFT JOIN task_params p ON p.task_id=t.id'
                " AND p.name='rappel'"
                " WHERE t.invocation_id='envoyer_par_le_web'"
                ' ORDER BY t.rowid'
            )
        ]

    def test_un_message_d_essai_qui_attend_repart_tout_seul(self) -> None:
        """Le bouton de la page Système : Serge demande le contact, puis
        retourne voir dix minutes plus tard, avec le même texte."""
        self.modeles.envoi = {'envoye': 'attente', 'raison': DEMANDE}
        self._essai('Bonjour, ceci est un essai.')
        self.assertEqual(
            self._essais(), [('done', 'attente', ''), ('ready', '', '2')]
        )
        quand = self._reprise('envoyer_par_le_web')
        self.assertEqual(
            round((quand - datetime.now(UTC)).total_seconds() / 60), 10
        )
        # Tu as accepté : au rappel, le texte part, et rien ne suit.
        self.modeles.envoi = {'envoye': 'oui', 'reference': FIL}
        self._le_temps_passe(invocation='envoyer_par_le_web')
        self.assertEqual(
            self._essais(), [('done', 'attente', ''), ('done', 'oui', '2')]
        )
        self.assertEqual(
            [(e['adresse'], e['message']) for e in self.modeles.envois],
            [('ana_roux', 'Bonjour, ceci est un essai.')] * 2,
        )
        # Un essai n'écrit aucun envoi.
        self.assertEqual(self._un('SELECT COUNT(*) FROM touches')[0], 0)

    def test_un_message_d_essai_ne_repart_pas_sans_fin(self) -> None:
        """Personne n'accepte : Serge essaie le nombre de fois réglé (la
        première comprise), puis s'arrête."""
        self._regler('compter_rappels_essai', 'essais_max', 3)
        self.modeles.envoi = {'envoye': 'attente', 'raison': DEMANDE}
        self._essai('Bonjour.')
        for _ in range(5):
            self._le_temps_passe(invocation='envoyer_par_le_web')
        self.assertEqual(
            self._essais(),
            [
                ('done', 'attente', ''),
                ('done', 'attente', '2'),
                ('done', 'attente', '3'),
            ],
        )

    def test_sans_compte_le_canal_n_est_pas_branche(self) -> None:
        self._compte('blocked')
        self.assertEqual(
            self._un(
                'SELECT etat, connected, polls FROM canaux WHERE id=?',
                'linkedin',
            ),
            ('prevu', 0, 0),
        )
        campagne = self._un_envoi_pret()
        self._vider()
        etat, raison = self._un(
            'SELECT state, end_reason FROM campaigns WHERE venture_id=?',
            campagne,
        )
        self.assertEqual(etat, 'CANCELLED')
        self.assertIn('linkedin', raison)
        self.assertEqual(self._un('SELECT COUNT(*) FROM touches')[0], 0)

    def test_les_deux_boutons_d_essai(self) -> None:
        """Page Système : un message d'essai et la lecture d'une
        conversation passent par les invocations des vrais canaux, sans
        contact ni campagne ; la personne se donne par l'adresse de son
        profil ou par son pseudo."""
        from serge.interpreter.triggers import fire_button

        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_message_d_essai_reseau',
                {
                    'nom du compte (linkedin, instagram, x…)': 'linkedin',
                    A_QUI: ANA,
                    'texte du message (280 caractères au plus pour'
                    ' LinkedIn)': 'Bonjour, ceci est un essai.',
                },
            )
        )
        self.modeles.recus = [{'de': ANA, 'texte': 'Bien reçu.'}]
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_lire_conversation_reseau',
                {
                    'nom du compte (linkedin, instagram, x…)': 'linkedin',
                    'de qui lire la réponse : son pseudo sur ce réseau, ou'
                    " l'adresse de son profil": ANA,
                },
            )
        )
        # Un pseudo suffit : il arrive tel quel à l'invocation, qui trouve
        # le profil par la recherche du site.
        self.assertIsNotNone(
            fire_button(
                self.conn,
                'bouton_message_d_essai_reseau',
                {
                    'nom du compte (linkedin, instagram, x…)': 'linkedin',
                    A_QUI: 'ana_roux',
                    'texte du message (280 caractères au plus pour'
                    ' LinkedIn)': 'Second essai.',
                },
            )
        )
        self.conn.commit()
        self._vider()
        self.assertEqual(
            [e['adresse'] for e in self.modeles.envois], [ANA, 'ana_roux']
        )
        envoi = self.modeles.envois[0]
        self.assertEqual(
            (
                envoi['compte'],
                envoi['adresse'],
                envoi['message'],
                envoi['sorte'],
            ),
            ('linkedin', ANA, 'Bonjour, ceci est un essai.', 'first'),
        )
        rendus = [
            json.loads(r[0])
            for r in self.conn.execute(
                'SELECT answer_json FROM tasks WHERE invocation_id IN'
                " ('envoyer_par_le_web', 'lire_messagerie')"
                ' ORDER BY invocation_id'
            )
        ]
        self.assertEqual(
            [r.get('envoye') for r in rendus], ['oui', 'oui', None]
        )
        self.assertEqual(rendus[2]['messages'][0]['texte'], 'Bien reçu.')
        # Un essai n'écrit ni envoi ni message reçu.
        self.assertEqual(self._un('SELECT COUNT(*) FROM touches')[0], 0)
        self.assertEqual(self._un('SELECT COUNT(*) FROM inbound_events')[0], 0)

    def test_une_adresse_de_profil_se_compare(self) -> None:
        for ecrite in (
            'https://www.linkedin.com/in/Ana-Roux/?trk=public',
            'http://linkedin.com/in/ana-roux#apropos',
        ):
            self.assertEqual(
                normalise_value('linkedin', ecrite), 'linkedin.com/in/ana-roux'
            )
        # Un pseudo n'est pas une adresse : il garde ses majuscules.
        self.assertEqual(normalise_value('pigeon', 'Colombe-12'), 'Colombe-12')


if __name__ == '__main__':
    unittest.main()
