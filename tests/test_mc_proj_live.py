#!/usr/bin/env python3
"""Projecteurs P0 : golden sur fixtures (hero, urgents, file, feed, jauges)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.mc.proj_live import (  # noqa: E402
    project_feed,
    project_file,
    project_file_detail,
    project_hero,
    project_jauges,
    project_urgents,
)
from serge.scheduler import claim, enqueue  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {
        'email_per_mailbox_per_day': 40,
        'voice_max_calls_per_day': 50,
        'linkedin_connect_per_day': 20,
    },
}


class ProjLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email,'
            " regime, funnel_state, created_at, updated_at) VALUES('p1','v1',"
            "'Ada','ada@x.io','OUTBOUND','CONTACTING','t','t')"
        )
        running = enqueue(
            self.conn,
            kind='email.send',
            idempotency_key='k-run',
            venture_id='v1',
        )
        claim(self.conn, running)
        first = enqueue(
            self.conn,
            kind='inbound.classify',
            idempotency_key='k-r1',
            venture_id='v1',
        )
        enqueue(
            self.conn,
            kind='inbound.classify',
            idempotency_key='k-r2',
            venture_id='v1',
        )
        self.conn.execute(
            "UPDATE work_items SET created_at='2026-09-10T10:00:00+00:00'"
            ' WHERE id=?',
            (first,),
        )
        self.conn.execute(
            "UPDATE work_items SET created_at='2026-09-10T11:00:00+00:00'"
            " WHERE status='RUNNING'"
        )
        for tid, typ, title, expiry in (
            ('t-guichet', 'GUICHET', 'Captcha', '2026-09-10T12:10:00+00:00'),
            ('t-veto30', 'VETO_AMONT', 'Prix', '2026-09-10T12:30:00+00:00'),
            ('t-veto2h', 'VETO_AMONT', 'Tard', '2026-09-10T14:00:00+00:00'),
            ('t-alert', 'ALERT', 'Quota', ''),
            ('t-hypo', 'HYPOTHESIS', 'H1', ''),
        ):
            self.conn.execute(
                'INSERT INTO tickets(id, type, title, state, expiry_at,'
                " created_at, updated_at) VALUES(?,?,?,'OPEN',?,?,?)",
                (tid, typ, title, expiry, NOW, NOW),
            )
        self.conn.execute(
            'INSERT INTO ticket_events(ticket_id, ts, actor, kind)'
            " VALUES('t-guichet','2026-09-10T11:30:00+00:00','serge','created')"
        )
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            " status, idempotency_key, created_at, updated_at) VALUES('t1',"
            "'c1','p1','email','sent','k-t1',?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            " status, idempotency_key, created_at, updated_at) VALUES('t0',"
            "'c1','p1','email','sent','k-t0','2026-09-09T10:00:00+00:00',"
            "'2026-09-09T10:00:00+00:00')"
        )
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            " tokens_out, latency_ms, verdict, created_at) VALUES('classify',"
            "'T1','m',1000,500,10,'ok',?)",
            (NOW,),
        )
        append_event(
            self.conn, actor='runner', type='cycle', payload={'done': 1}
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_hero_running_et_ready(self) -> None:
        hero = project_hero(self.conn, POLICY, NOW)
        self.assertEqual(hero['running']['kind'], 'email.send')
        self.assertEqual(hero['running']['venture_id'], 'v1')
        self.assertEqual(hero['ready'], 2)
        self.assertEqual(hero['next']['kind'], 'inbound.classify')

    def test_urgents_ordonnes(self) -> None:
        items = project_urgents(self.conn, POLICY, NOW)['items']
        self.assertEqual(
            [item['id'] for item in items],
            ['t-guichet', 't-veto30', 't-alert'],
        )

    def test_file_next_fifo(self) -> None:
        file = project_file(self.conn, POLICY, NOW)
        self.assertEqual(len(file['running']), 1)
        self.assertEqual(file['ready_count'], 2)
        conn = self.conn.execute(
            "SELECT id FROM work_items WHERE created_at LIKE '2026-09-10T10%'"
        ).fetchone()[0]
        self.assertEqual(file['next']['id'], conn)

    def test_file_detail_ordre_et_libelles(self) -> None:
        fiche = project_file_detail(self.conn, NOW)
        self.assertEqual(fiche['type'], 'file')
        lignes = fiche['tableau']['lignes']
        self.assertEqual(len(lignes), 3)
        self.assertEqual(lignes[0]['cellules'][1], 'Envoi d’e-mail')
        self.assertEqual(lignes[0]['cellules'][2], 'En cours')
        self.assertEqual(lignes[1]['cellules'][2], 'Prochain')
        self.assertEqual(lignes[1]['cellules'][1], 'Classification d’une réponse')
        self.assertEqual(lignes[2]['cellules'][2], 'Prêt')

    def test_feed_tri_et_sources(self) -> None:
        items = project_feed(self.conn, POLICY, NOW)['items']
        stamps = [item['ts'] for item in items]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        self.assertEqual(
            {item['source'] for item in items}, {'event', 'ticket', 'touche'}
        )
        self.assertLessEqual(len(items), 30)

    def test_jauges_llm_et_email(self) -> None:
        jauges = project_jauges(self.conn, POLICY, NOW)
        llm = jauges['llm']
        self.assertEqual(llm['tokens_jour'], 1500)
        self.assertAlmostEqual(llm['eur_estimes'], 0.006)
        self.assertAlmostEqual(llm['ratio'], 0.0012)
        email = jauges['email']
        self.assertEqual((email['envoyes'], email['quota']), (1, 40))
        self.assertEqual(email['libelle'], 'E-mails')
        self.assertAlmostEqual(email['ratio'], 0.025)
        self.assertEqual(jauges['voix']['libelle'], 'Appels')
        self.assertEqual((jauges['voix']['faits'], jauges['voix']['quota']), (0, 50))
        self.assertEqual(jauges['linkedin']['libelle'], 'Invitations LinkedIn')
        self.assertEqual(jauges['linkedin']['quota'], 20)


if __name__ == '__main__':
    unittest.main()
