#!/usr/bin/env python3
"""Une source : le dernier snapshot du canon, YAML = semence."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.policy import load_policy  # noqa: E402
from serge.policy_snapshots import (  # noqa: E402
    latest_policy,
    policy_en_vigueur,
    snapshot_policy,
)


class PolicyEnVigueurTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_semence_puis_snapshot_gagne(self) -> None:
        self.assertIsNone(latest_policy(self.conn))
        seed = policy_en_vigueur(self.conn)
        self.assertEqual(seed['budget']['llm_daily_eur'], 5.0)
        self.assertEqual(seed['testing']['n_smoke_min'], 30)
        self.assertEqual(
            self.conn.execute(
                'SELECT applied_by FROM policy_snapshots'
            ).fetchone()[0],
            'seed',
        )
        mod = dict(seed)
        mod['budget'] = dict(seed['budget'])
        mod['budget']['llm_daily_eur'] = 12.5
        snapshot_policy(self.conn, mod, applied_by='owner')
        live = policy_en_vigueur(self.conn)
        self.assertEqual(live['budget']['llm_daily_eur'], 12.5)
        self.assertEqual(load_policy()['budget']['llm_daily_eur'], 5.0)


if __name__ == '__main__':
    unittest.main()
