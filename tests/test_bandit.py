#!/usr/bin/env python3
"""Bandit Thompson : parts normalisées, équi sans données, rejeu."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.allocator.bandit import propose_bandit  # noqa: E402
from serge.db.schema import init_schema  # noqa: E402

POLICY = {
    'budget': {'allocator_bandit_cost_per_eur': 10.0},
    'prospection': {'score_w_intent': 25, 'score_w_reply': 10},
}
NOW = '2026-09-09T19:00:00+00:00'


class BanditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        for campaign in ('c1', 'c2'):
            self.conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel,'
                " state, created_at, updated_at) VALUES(?,'v1','named',"
                "'email','RUNNING','t','t')",
                (campaign,),
            )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_equi_sans_donnees(self) -> None:
        result = propose_bandit(self.conn, POLICY, 'v1', seed=7)
        self.assertEqual(result['allocations'], {'c1': 0.5, 'c2': 0.5})

    def test_gagnant_favorise(self) -> None:
        for index in range(10):
            self.conn.execute(
                'INSERT INTO touches(id, campaign_id, channel, status,'
                ' cost_eur, idempotency_key, created_at, updated_at)'
                " VALUES(?,?,'email','sent',0.01,?,?,?)",
                (f't{index}', 'c1', f'k{index}', NOW, NOW),
            )
        self.conn.execute(
            'INSERT INTO inbound_events(id, campaign_id, channel,'
            " native_type, signal, received_at) VALUES('e0','c1','email',"
            "'X','INTENT',?)",
            (NOW,),
        )
        result = propose_bandit(self.conn, POLICY, 'v1', seed=7)
        total = sum(result['allocations'].values())
        self.assertAlmostEqual(total, 1.0, places=3)
        self.assertGreater(
            result['allocations']['c1'], result['allocations']['c2']
        )

    def test_rejeu_deterministe(self) -> None:
        first = propose_bandit(self.conn, POLICY, 'v1', seed=42)
        second = propose_bandit(self.conn, POLICY, 'v1', seed=42)
        self.assertEqual(first['allocations'], second['allocations'])

    def test_sans_campagne_vide(self) -> None:
        result = propose_bandit(self.conn, POLICY, 'vZZ', seed=1)
        self.assertEqual(result['allocations'], {})


if __name__ == '__main__':
    unittest.main()
