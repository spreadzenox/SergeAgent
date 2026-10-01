#!/usr/bin/env python3
"""Projecteurs P5 Politique : tests unitaires et goldens."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_policy import (  # noqa: E402
    project_politique_active,
    project_testing_froid,
)
from serge.policy import load_policy  # noqa: E402
from serge.policy_snapshots import snapshot_policy  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'


class ProjPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.policy = load_policy()

    def test_politique_active(self) -> None:
        res = project_politique_active(self.conn, self.policy, NOW)
        self.assertIn('policy', res)
        self.assertEqual(res['policy']['schema_version'], 1)

    def test_testing_froid_lock(self) -> None:
        res0 = project_testing_froid(self.conn, self.policy, NOW)
        self.assertFalse(res0['is_locked'])
        self.assertEqual(res0['running_campaigns'], 0)
        self.assertEqual(res0['config']['n_smoke_min'], 30)
        seeded = dict(self.policy)
        seeded['testing'] = {**res0['config'], 'n_smoke_min': 40}
        snapshot_policy(self.conn, seeded, applied_by='owner')
        res_t = project_testing_froid(self.conn, self.policy, NOW)
        self.assertEqual(res_t['config']['n_smoke_min'], 40)

        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state, n_target, created_at, updated_at)'
            " VALUES('c1', 'v1', 'named', 'email', 'RUNNING', 10, 't', 't')"
        )
        res1 = project_testing_froid(self.conn, self.policy, NOW)
        self.assertTrue(res1['is_locked'])
        self.assertEqual(res1['running_campaigns'], 1)


if __name__ == '__main__':
    unittest.main()
