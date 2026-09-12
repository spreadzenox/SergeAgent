#!/usr/bin/env python3
"""Taille des essais : N et seuils = policy MC, pas le TOML."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.campaigns import (  # noqa: E402
    n_reached,
    thresholds,
    to_ready,
)
from serge.funnels.essai import (  # noqa: E402
    evaluer_campagne,
    ouvrir_essai,
    testing_en_vigueur,
)
from serge.policy_snapshots import (  # noqa: E402
    policy_en_vigueur,
    snapshot_policy,
)


class EssaiLiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_ouvrir_smoke_lit_le_snapshot(self) -> None:
        pol = policy_en_vigueur(self.conn)
        self.assertEqual(testing_en_vigueur(self.conn)['n_smoke_min'], 30)
        pol = dict(pol)
        pol['testing'] = {
            **testing_en_vigueur(self.conn),
            'n_smoke_min': 42,
            'scale_min_positives': 7,
        }
        snapshot_policy(self.conn, pol, applied_by='owner')
        cid = ouvrir_essai(self.conn, 'v1', 'named', 'email', 'smoke')
        self.assertEqual(
            self.conn.execute(
                'SELECT n_target FROM campaigns WHERE id=?', (cid,)
            ).fetchone()[0],
            42,
        )
        th = thresholds(self.conn, cid)
        self.assertEqual(th['phase'], 'smoke')
        self.assertEqual(th['scale_min_positifs'], 7)
        to_ready(self.conn, cid)
        self.assertFalse(n_reached(self.conn, cid))
        self.assertEqual(
            evaluer_campagne(
                self.conn, cid, n_atteint=True, fenetre_ecoulee=True
            ),
            'FULL',
        )

    def test_ouvrir_full_lit_n_cible(self) -> None:
        pol = dict(policy_en_vigueur(self.conn))
        pol['testing'] = {
            **testing_en_vigueur(self.conn),
            'n_full_target': 180,
        }
        snapshot_policy(self.conn, pol, applied_by='owner')
        cid = ouvrir_essai(self.conn, 'v1', 'named', 'email', 'full')
        self.assertEqual(
            self.conn.execute(
                'SELECT n_target FROM campaigns WHERE id=?', (cid,)
            ).fetchone()[0],
            180,
        )


if __name__ == '__main__':
    unittest.main()
