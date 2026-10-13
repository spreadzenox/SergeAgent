#!/usr/bin/env python3
"""Page Système : les îlots, un par morceau de Serge qui tourne."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.discord.forum import ECHEC, regler_forum  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_ilots import project_ilots  # noqa: E402
from tests.taches_fixtures import invocations, tache  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}


class ProjSystemFixtures(unittest.TestCase):
    """Fixtures P1 partagées (sans test — base des goldens de la page Système)."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn
        conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v2','CANDIDATE',0,'t','t')"
        )
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                'OUTBOUND',
                'CONTACTING',
                't',
                't',
            ),
        )
        add_address(conn, 'p1', 'email', 'ada@x.io')
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'p2',
                'v1',
                'Bob',
                'OUTBOUND',
                'NEW',
                't',
                't',
            ),
        )
        add_address(conn, 'p2', 'email', 'bob@x.io')
        conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, created_at, updated_at) VALUES'
            "('c1','v1','named','email','RUNNING',10,'t','t')"
        )
        conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, created_at, updated_at) VALUES'
            "('c2','v1','named','sms','DRAFT',5,'t','t')"
        )
        conn.execute(
            "UPDATE campaigns SET updated_at='2026-09-10T11:30:00+00:00'"
            " WHERE id='c1'"
        )
        conn.execute(
            "UPDATE campaigns SET updated_at='2026-09-10T11:00:00+00:00'"
            " WHERE id='c2'"
        )
        for tid, cid, pid, channel, statut, cle, updated in (
            (
                't1',
                'c1',
                'p1',
                'email',
                'sent',
                'k-t1',
                '2026-09-10T11:30:00+00:00',
            ),
            (
                't2',
                'c1',
                'p1',
                'email',
                'queued',
                'k-t2',
                '2026-09-10T11:00:00+00:00',
            ),
            (
                't3',
                'c2',
                'p2',
                'sms',
                'sent',
                'k-t3',
                '2026-09-10T11:00:00+00:00',
            ),
        ):
            conn.execute(
                'INSERT INTO touches(id, campaign_id, contact_id, channel,'
                ' status, idempotency_key, created_at, updated_at) VALUES'
                '(?,?,?,?,?,?,?,?)',
                (
                    tid,
                    cid,
                    pid,
                    channel,
                    statut,
                    cle,
                    '2026-09-10T11:00:00+00:00',
                    updated,
                ),
            )
        invocations(
            conn,
            ('envoyer', 'Envoyer un e-mail', 'prospection_light'),
            ('classer', 'Classer une réponse', 'prospection_lourde'),
            ('ramasser', 'Ramasser des pages', 'pre_prospection'),
            ('relever', 'Relever la boîte', 'prospection_lourde'),
        )
        v1 = {'venture_id': 'v1'}
        tache(
            conn,
            'envoyer',
            v1,
            key='k-run',
            status='running',
            created_at='2026-09-10T11:30:00+00:00',
        )
        self.w_ready = tache(conn, 'classer', v1, key='k-r1')
        tache(
            conn,
            'ramasser',
            v1,
            key='k-r2',
            not_before='2026-09-10T13:00:00+00:00',
        )
        tache(conn, 'relever', v1, key='k-f1', status='failed')
        append_event(
            conn, actor='guards', type='guard', payload={'allowed': True}
        )
        append_event(
            conn,
            actor='guards',
            type='guard',
            payload={'allowed': False, 'code': 'deny'},
        )
        append_event(
            conn, actor='guards', type='guard', payload={'allowed': True}
        )
        conn.execute(
            "UPDATE events SET ts='2026-09-10T11:05:00+00:00' WHERE id=("
            "SELECT MIN(id) FROM events WHERE actor='guards')"
        )
        conn.execute(
            "UPDATE events SET ts='2026-09-10T11:06:00+00:00'"
            " WHERE payload_json LIKE '%deny%'"
        )
        conn.execute(
            "UPDATE events SET ts='2026-09-08T11:00:00+00:00' WHERE id=("
            "SELECT MAX(id) FROM events WHERE actor='guards')"
        )
        conn.execute(
            'INSERT INTO listen_docs(id, source, fetched_at) VALUES'
            "('d1','rss','2026-09-10T11:00:00+00:00')"
        )
        conn.execute(
            'INSERT INTO listen_docs(id, source, fetched_at) VALUES'
            "('d2','rss','2026-09-08T11:00:00+00:00')"
        )
        conn.execute(
            'INSERT INTO inbound_events(id, channel, native_type, signal,'
            " received_at) VALUES('b1','sms','MO','reply',"
            "'2026-09-10T11:20:00+00:00')"
        )


class ProjIlotsTests(ProjSystemFixtures):
    def setUp(self) -> None:
        super().setUp()
        # Les services de la machine : aucun ici, sauf ceux d'un test.
        self.services: dict[str, str] = {}
        patch = mock.patch(
            'serge.mc.proj_ilots.etat_service',
            side_effect=lambda unit: self.services.get(unit, 'inconnu'),
        )
        patch.start()
        self.addCleanup(patch.stop)

    def _ilot(self, ident: str) -> dict:
        return {
            i['id']: i for i in project_ilots(self.conn, POLICY, NOW)['items']
        }[ident]

    def test_ilots_golden(self) -> None:
        self.assertEqual(
            project_ilots(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'id': 'taches',
                        'label': 'Files de tâches',
                        'sante': 'erreur',
                        'activite': 0.3,
                        'resume': '1 en cours, 2 prêtes, 1 en attente de'
                        ' leur heure, 1 échouées (24 h)',
                        'details': [
                            'File des conversations : état inconnu.',
                            'File des travaux : état inconnu.',
                        ],
                    },
                    {
                        'id': 'email',
                        'label': 'E-mail',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Pas branché sur ce serveur.',
                        'details': [],
                    },
                    {
                        'id': 'voice',
                        'label': 'Voix',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Pas branché sur ce serveur.',
                        'details': [],
                    },
                    {
                        'id': 'discord',
                        'label': 'Discord',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Pas branché : pas de bot sur ce serveur,'
                        ' ni forum, ni administrateur.',
                        'details': [],
                    },
                    {
                        'id': 'listen',
                        'label': 'Écoute',
                        'sante': 'ok',
                        'activite': 0.05,
                        'resume': '1 pages lues (24 h)',
                        'details': [],
                    },
                    {
                        'id': 'guards',
                        'label': 'Garde-fous',
                        'sante': 'ok',
                        'activite': 0.1,
                        'resume': '2 verdicts, 1 refus (24 h)',
                        'details': [],
                    },
                ]
            },
        )

    def test_un_canal_branche_dit_ce_qui_part_et_arrive(self) -> None:
        """L'e-mail branché : partis et reçus sur 24 h, sa dernière relève ;
        une boîte pas relevée depuis plus d'une heure est « dégradée »."""
        self.conn.execute(
            "UPDATE canaux SET etat='branche', polls=1,"
            " polled_at='2026-09-10T11:50:00+00:00' WHERE id='email'"
        )
        self.conn.execute(
            "UPDATE touches SET sent_at='2026-09-10T11:00:00+00:00'"
            " WHERE channel='email' AND status='sent'"
        )
        self.conn.execute(
            'INSERT INTO inbound_events(id, channel, received_at) VALUES'
            "('r1', 'email', '2026-09-10T11:30:00+00:00')"
        )
        email = self._ilot('email')
        self.assertEqual(
            (email['sante'], email['resume']),
            ('ok', '1 partis, 1 reçus (24 h), relevé à 11:50'),
        )
        self.conn.execute(
            "UPDATE canaux SET polled_at='2026-09-10T09:00:00+00:00'"
            " WHERE id='email'"
        )
        self.assertEqual(self._ilot('email')['sante'], 'degrade')

    def test_la_voix_dit_l_etat_du_pont_vocal(self) -> None:
        self.conn.execute("UPDATE canaux SET etat='branche' WHERE id='voice'")
        self.services['serge-voice-bridge.service'] = 'active'
        voix = self._ilot('voice')
        self.assertEqual(
            (voix['sante'], voix['details']),
            ('ok', ['Pont vocal : en marche.']),
        )
        self.services['serge-voice-bridge.service'] = 'failed'
        voix = self._ilot('voice')
        self.assertEqual(
            (voix['sante'], voix['details']),
            ('erreur', ['Pont vocal : en panne.']),
        )

    def test_une_file_arretee_est_en_erreur(self) -> None:
        self.conn.execute("DELETE FROM tasks WHERE status='failed'")
        self.services['serge-queue@conversations.service'] = 'active'
        self.services['serge-queue@works.service'] = 'active'
        self.assertEqual(self._ilot('taches')['sante'], 'ok')
        self.services['serge-queue@works.service'] = 'inactive'
        taches = self._ilot('taches')
        self.assertEqual(taches['sante'], 'erreur')
        self.assertIn('File des travaux : arrêté.', taches['details'])

    def test_taches_pretes_non_servies_degrade(self) -> None:
        self.conn.execute("DELETE FROM tasks WHERE status='failed'")
        self.conn.execute('UPDATE invocations SET enabled=0')
        taches = self._ilot('taches')
        self.assertEqual(taches['sante'], 'degrade')
        self.assertIn('voir En direct', taches['details'][-1])

    def test_une_tache_en_cours_depuis_longtemps_degrade(self) -> None:
        self.conn.execute('DELETE FROM tasks')
        tache(
            self.conn,
            'envoyer',
            key='k-vieux',
            status='running',
            created_at='2026-09-10T10:00:00+00:00',
        )
        taches = self._ilot('taches')
        self.assertEqual(taches['sante'], 'degrade')
        self.assertIn(
            '1 en cours depuis plus de 30 minutes.', taches['details']
        )

    def test_discord_dit_le_bot_le_forum_et_les_administrateurs(
        self,
    ) -> None:
        """Le bot en marche sans forum ni administrateur : dégradé. Avec
        les deux : en forme. Un fil pas ouvert : dégradé. Le bot arrêté :
        en erreur."""
        self.services['serge-discord-bot.service'] = 'active'
        discord = self._ilot('discord')
        self.assertEqual(discord['sante'], 'degrade')
        self.assertIn('Pas de forum réglé', discord['details'][1])
        self.assertIn('Aucun administrateur', discord['details'][2])
        regler_forum(self.conn, '222233334444555566', 'owner')
        self.conn.execute(
            'INSERT INTO discord_admins(user_id, name, added_by, added_at)'
            " VALUES('123456789012345678', 'Clem', 'mc', ?)",
            (NOW,),
        )
        self.conn.execute(
            'INSERT INTO ticket_posts(ticket_id, thread_id, shown_state,'
            " updated_at) VALUES('k1', 'fil1', 'OPEN@t', ?)",
            (NOW,),
        )
        discord = self._ilot('discord')
        self.assertEqual(
            (discord['sante'], discord['resume'], discord['details']),
            (
                'ok',
                '1 administrateurs, 0 tickets ouverts, 1 cartes envoyées ou'
                ' mises à jour (24 h)',
                [
                    'Bot : en marche.',
                    'Forum des tickets : 222233334444555566.',
                    'Administrateurs : Clem.',
                ],
            ),
        )
        self.conn.execute(
            "UPDATE ticket_posts SET thread_id='', shown_state=?", (ECHEC,)
        )
        discord = self._ilot('discord')
        self.assertEqual(discord['sante'], 'degrade')
        self.assertIn('1 fils pas ouverts', discord['details'][3])
        self.services['serge-discord-bot.service'] = 'failed'
        self.assertEqual(self._ilot('discord')['sante'], 'erreur')


if __name__ == '__main__':
    unittest.main()
