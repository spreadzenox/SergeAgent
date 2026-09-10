#!/usr/bin/env python3
"""Runner : cycle (expiry, dispatch, retry, consolidation, crash-safe)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.memory.summaries import put_summary  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.runner import run_once  # noqa: E402
from serge.scheduler import enqueue  # noqa: E402
from serge.tickets import create_ticket, publish  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {
        'other_batch_max_items': 20,
        'tech_fail_pattern_per_week': 3,
    },
    'memory': {
        'consolidation_days': 3,
        'consolidate_max_items': 10,
        'serge_md_max_lines': 100,
    },
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}
NOW = '2026-09-09T19:00:00+00:00'


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def test_idle_expire_et_consolidation(self) -> None:
        ticket_id = create_ticket(
            self.conn, self.types, 'QNA', 'q', {'question': 'x?'}, now=NOW
        )
        publish(self.conn, ticket_id)
        result = run_once(self.conn, POLICY, now='2026-09-20T19:00:00+00:00')
        self.assertEqual(result['processed'], 0)
        self.assertEqual(result['expired'], 1)
        self.assertTrue(result['consolidation'])
        kinds = [
            row[0] for row in self.conn.execute('SELECT kind FROM work_items')
        ]
        self.assertIn('memory.consolidate', kinds)

    def test_cycle_ecrit_event_resume(self) -> None:
        result = run_once(self.conn, POLICY, now=NOW)
        row = self.conn.execute(
            "SELECT payload_json FROM events WHERE type='cycle'"
            ' ORDER BY id DESC LIMIT 1'
        ).fetchone()
        payload = json.loads(row[0])
        self.assertEqual(
            (payload['processed'], payload['done'], payload['failed']),
            (result['processed'], result['done'], result['failed']),
        )
        self.assertEqual(payload['expired'], result['expired'])
        self.assertGreaterEqual(payload['duration_ms'], 0)

    def test_dispatch_done_et_failed(self) -> None:
        enqueue(
            self.conn,
            kind='inbound.judge_other',
            idempotency_key='k-j',
            venture_id='v1',
            payload={},
        )
        enqueue(
            self.conn,
            kind='nope.kind',
            idempotency_key='k-n',
            venture_id='v1',
            payload={},
        )
        put_summary(self.conn, 'consolidation', NOW)
        result = run_once(self.conn, POLICY, now=NOW)
        self.assertEqual(
            (result['processed'], result['done'], result['failed']),
            (2, 1, 1),
        )
        self.assertFalse(result['consolidation'])
        statuses = {
            row[0]: row[1]
            for row in self.conn.execute(
                'SELECT idempotency_key, status FROM work_items'
                ' WHERE idempotency_key IN (?,?)',
                ('k-j', 'k-n'),
            )
        }
        self.assertEqual(statuses, {'k-j': 'DONE', 'k-n': 'FAILED'})


if __name__ == '__main__':
    unittest.main()
