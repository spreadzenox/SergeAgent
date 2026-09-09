#!/usr/bin/env python3
"""Point A1 : juge allocation, clamps + justifs + tickets."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.points.allocator import judge_allocation  # noqa: E402

POLICY = {
    'budget': {
        'llm_daily_eur': 5.0,
        'llm_eur_per_1k_tokens': 0.004,
        'allocator_reserve_ratio': 0.20,
        'allocator_max_unproven_ratio': 0.30,
        'allocator_max_single_channel_ratio': 0.60,
        'allocator_reversal_points': 10,
        'allocator_bandit_gap_points': 15,
    },
    'quotas': {'llm_recalls_json': 1},
}
B = {'c1': 0.5, 'c2': 0.5}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class AllocatorJudgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_juge_clampe(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'allocations': {'c1': 0.95, 'c2': 0.05},
                    'mouvements': [],
                    'justifications': {'c1': 'momentum fort'},
                }
            )
        )
        result = judge_allocation(
            self.conn, POLICY, 'état', B, {'c1', 'c2'}, caller=caller
        )
        self.assertLessEqual(result['allocations']['c1'], 0.49)
        self.assertTrue(result['log'])

    def test_irreversible_vers_tickets(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'allocations': {'c1': 0.5, 'c2': 0.5},
                    'mouvements': [
                        {
                            'type': 'kill',
                            'cible': 'c2',
                            'detail': 'x',
                            'irreversible': True,
                        },
                        {
                            'type': 'pauser',
                            'cible': 'c1',
                            'detail': 'y',
                            'irreversible': False,
                        },
                    ],
                    'justifications': {},
                }
            )
        )
        result = judge_allocation(
            self.conn, POLICY, 'état', B, {'c1', 'c2'}, caller=caller
        )
        self.assertEqual(len(result['tickets_needed']), 1)
        self.assertEqual(len(result['mouvements']), 1)

    def test_ecart_non_justifie_flag(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'allocations': {'c1': 0.9, 'c2': 0.1},
                    'mouvements': [],
                    'justifications': {},
                }
            )
        )
        result = judge_allocation(
            self.conn, POLICY, 'état', B, {'c1', 'c2'}, caller=caller
        )
        self.assertTrue(result['ecart_non_justifie'])

    def test_repli_b_brute(self) -> None:
        caller = _caller_for('no json')
        result = judge_allocation(
            self.conn, POLICY, 'état', B, {'c1', 'c2'}, caller=caller
        )
        self.assertTrue(result['fallback'])
        self.assertAlmostEqual(
            sum(result['allocations'].values()), 0.8, places=3
        )


if __name__ == '__main__':
    unittest.main()
