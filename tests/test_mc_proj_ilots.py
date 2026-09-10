#!/usr/bin/env python3
"""Projecteurs P1 : goldens îlots/scheduler/campagnes/population/email."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.mc.proj_ilots import (  # noqa: E402
    project_ilots,
    project_scheduler,
)
from serge.scheduler import claim, enqueue  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}


class ProjSystemFixtures(unittest.TestCase):
    """Fixtures P1 partagées (sans test — base des goldens îlots/campagnes)."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
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
            'INSERT INTO contacts(id, venture_id, display, email,'
            " regime, funnel_state, created_at, updated_at) VALUES('p1','v1',"
            "'Ada','ada@x.io','OUTBOUND','CONTACTING','t','t')"
        )
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email,'
            " regime, funnel_state, created_at, updated_at) VALUES('p2','v1',"
            "'Bob','bob@x.io','OUTBOUND','NEW','t','t')"
        )
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
        conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            ' intent_id, status, created_at, updated_at) VALUES'
            "('x1','v1','invoice',100.0,'in-1','paid','t','t')"
        )
        conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            ' intent_id, status, created_at, updated_at) VALUES'
            "('x2','v1','invoice',50.0,'in-2','overdue','t','t')"
        )
        conn.execute(
            'INSERT INTO accounts_standing(id, venue, handle, cooldown_until,'
            " updated_at) VALUES('s1','gmail','a@x.io',"
            "'2026-09-10T14:00:00+00:00','t')"
        )
        conn.execute(
            'INSERT INTO accounts_standing(id, venue, handle, cooldown_until,'
            " updated_at) VALUES('s2','sms','+331',"
            "'2026-09-10T10:00:00+00:00','t')"
        )
        running = enqueue(
            conn, kind='email.send', idempotency_key='k-run', venture_id='v1'
        )
        claim(conn, running)
        conn.execute(
            "UPDATE work_items SET updated_at='2026-09-10T11:30:00+00:00'"
            ' WHERE id=?',
            (running,),
        )
        self.w_ready = enqueue(
            conn,
            kind='inbound.classify',
            idempotency_key='k-r1',
            venture_id='v1',
        )
        enqueue(
            conn,
            kind='listen.collect',
            idempotency_key='k-r2',
            venture_id='v1',
            blocked_until='2026-09-10T13:00:00+00:00',
        )
        failed = enqueue(
            conn, kind='email.poll', idempotency_key='k-f1', venture_id='v1'
        )
        conn.execute(
            "UPDATE work_items SET status='FAILED',"
            " updated_at='2026-09-10T11:15:00+00:00' WHERE id=?",
            (failed,),
        )
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
    def test_ilots_golden(self) -> None:
        self.assertEqual(
            project_ilots(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'id': 'scheduler',
                        'label': 'Ordonnanceur',
                        'sante': 'ok',
                        'activite': 0.3,
                        'resume': '2 prêts, 1 en cours, 1 bloqués',
                    },
                    {
                        'id': 'workers',
                        'label': 'Exécution',
                        'sante': 'erreur',
                        'activite': 0.3,
                        'resume': '1 en cours, 2 prêts, 1 échoués (24 h)',
                    },
                    {
                        'id': 'guards',
                        'label': 'Gardes',
                        'sante': 'ok',
                        'activite': 0.1,
                        'resume': '2 verdicts (1 refus)',
                    },
                    {
                        'id': 'funnels',
                        'label': 'Entonnoirs',
                        'sante': 'ok',
                        'activite': 0.15,
                        'resume': '2 ventures, 3 touches (24 h)',
                    },
                    {
                        'id': 'collect',
                        'label': 'Collecte',
                        'sante': 'erreur',
                        'activite': 0.2,
                        'resume': '2 intentions (1 payées), 1 en retard',
                    },
                    {
                        'id': 'listen',
                        'label': 'Écoute',
                        'sante': 'ok',
                        'activite': 0.05,
                        'resume': '1 documents (24 h)',
                    },
                    {
                        'id': 'allocator',
                        'label': 'Arbitre',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Pas de source (lot 6).',
                    },
                    {
                        'id': 'sms',
                        'label': 'SMS',
                        'sante': 'ok',
                        'activite': 0.2,
                        'resume': '1 envois, 1 reçus (24 h)',
                    },
                    {
                        'id': 'email',
                        'label': 'Email',
                        'sante': 'erreur',
                        'activite': 0.2,
                        'resume': '1 en file, 1 envoyés, 1 échoués (24 h)',
                    },
                    {
                        'id': 'discord',
                        'label': 'Discord',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Sonde gateway au lot 12.',
                    },
                    {
                        'id': 'voix',
                        'label': 'Voix',
                        'sante': 'inconnu',
                        'activite': 0.0,
                        'resume': 'Ledger voix au lot 11.',
                    },
                ]
            },
        )

    def test_scheduler_golden(self) -> None:
        self.assertEqual(
            project_scheduler(self.conn, POLICY, NOW),
            {
                'next': {
                    'id': self.w_ready,
                    'kind': 'inbound.classify',
                    'venture_id': 'v1',
                },
                'ready': 2,
                'running': 1,
                'bloques': 1,
            },
        )

    def test_scheduler_file_coincee_erreur(self) -> None:
        self.conn.execute('UPDATE ventures SET schedulable=0')
        projete = project_scheduler(self.conn, POLICY, NOW)
        self.assertIsNone(projete['next'])
        self.assertEqual(projete['ready'], 2)
        ilots = project_ilots(self.conn, POLICY, NOW)['items']
        self.assertEqual(ilots[0]['sante'], 'erreur')

    def test_workers_suspect_degrade(self) -> None:
        self.conn.execute('DELETE FROM work_items')
        self.conn.execute(
            'INSERT INTO work_items(id, kind, venture_id, status,'
            ' idempotency_key, created_at, updated_at) VALUES'
            "('w-vieux','email.send','v1','RUNNING','k-vieux',"
            "'2026-09-10T10:00:00+00:00','2026-09-10T10:00:00+00:00')"
        )
        ilots = project_ilots(self.conn, POLICY, NOW)['items']
        self.assertEqual(ilots[1]['sante'], 'degrade')
        self.assertEqual(ilots[0]['sante'], 'ok')
