#!/usr/bin/env python3
"""Consolidateur : échéance, batch → MEMORY + SERGE.md + FYI."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.memory.consolidate import (  # noqa: E402
    due_for_consolidation,
    gather_period,
    run_consolidation,
)
from serge.memory.summaries import put_summary  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'memory': {
        'consolidation_days': 3,
        'consolidate_max_items': 10,
        'serge_md_max_lines': 100,
    },
}
NOW = '2026-09-09T19:00:00+00:00'
D1 = json.dumps(
    {
        'lecons': [
            {
                'enonce': 'Relancer J+3.',
                'confiance': 0.7,
                'sources': ['e1'],
                'scope': 'global',
            }
        ],
        'playbooks': [],
        'pitfalls': [],
    }
)
D2 = json.dumps({'serge_md': '# Serge\nVenture : v1\n', 'changements': ['v1']})


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class ConsolidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_echeance(self) -> None:
        self.assertTrue(due_for_consolidation(self.conn, POLICY, NOW))
        put_summary(self.conn, 'consolidation', NOW)
        self.assertFalse(
            due_for_consolidation(
                self.conn, POLICY, '2026-09-10T19:00:00+00:00'
            )
        )
        self.assertTrue(
            due_for_consolidation(
                self.conn, POLICY, '2026-09-13T19:00:00+00:00'
            )
        )

    def test_gather(self) -> None:
        append_event(self.conn, actor='t', type='transition.x')
        matter = gather_period(self.conn, '')
        self.assertIn('transition.x', matter['episodes'])

    def test_batch_complet(self) -> None:
        caller = _caller_for(D1, D2)
        result = run_consolidation(self.conn, POLICY, caller=caller, now=NOW)
        self.assertTrue(result['due'])
        self.assertIsNotNone(result['ticket_id'])
        self.assertEqual(result['counts']['lecons'], 1)
        self.assertEqual(result['serge_md_version'], 1)
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (result['ticket_id'],)
        ).fetchone()[0]
        self.assertEqual(state, 'OPEN')
        kinds = [
            row[0]
            for row in self.conn.execute(
                'SELECT kind FROM ticket_items WHERE ticket_id=?',
                (result['ticket_id'],),
            )
        ]
        self.assertEqual(kinds, ['lesson'])
        self.assertFalse(due_for_consolidation(self.conn, POLICY, NOW))

    def test_vide_fyi(self) -> None:
        caller = _caller_for(
            json.dumps({'lecons': [], 'playbooks': [], 'pitfalls': []})
        )
        result = run_consolidation(self.conn, POLICY, caller=caller, now=NOW)
        self.assertIsNone(result['ticket_id'])
        self.assertIsNotNone(result['fyi_id'])
        self.assertEqual(result['fallback'], 'vide')

    def test_pas_du_pas_de_batch(self) -> None:
        put_summary(self.conn, 'consolidation', NOW)
        caller = _caller_for(D1, D2)
        result = run_consolidation(self.conn, POLICY, caller=caller, now=NOW)
        self.assertFalse(result['due'])
        self.assertEqual(caller.n, 0)


if __name__ == '__main__':
    unittest.main()
