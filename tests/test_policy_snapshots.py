#!/usr/bin/env python3
"""Une source : le dernier snapshot du canon, YAML = semence."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
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

    def test_snapshot_sans_standing_complete(self) -> None:
        import json

        seed = dict(load_policy())
        seed.pop('standing')
        self.conn.execute(
            'INSERT INTO policy_snapshots(content_hash, content_json,'
            " applied_by, active_from) VALUES('h1',?,'owner','t')",
            (json.dumps(seed),),
        )
        live = latest_policy(self.conn)
        self.assertEqual(live['standing']['cout_usage'], 0.10)
        self.assertEqual(live['standing']['capital_max'], 1.0)

    def test_une_section_retiree_de_la_semence_disparait(self) -> None:
        """Un ancien snapshot garde « listen » : elle ne revient pas."""
        import json

        ancien = dict(load_policy())
        ancien['listen'] = {'discovery_needs_target': 5}
        self.conn.execute(
            'INSERT INTO policy_snapshots(content_hash, content_json,'
            " applied_by, active_from) VALUES('h2',?,'owner','t')",
            (json.dumps(ancien),),
        )
        self.assertNotIn('listen', latest_policy(self.conn))

    def test_un_ancien_snapshot_avec_le_taux_estime_reste_valide(self) -> None:
        """L'estimation des jetons est retirée ; un ancien snapshot qui a
        encore ``budget.llm_eur_per_1k_tokens`` se charge, et la valeur
        (ignorée) n'empêche rien."""
        import json

        ancien = dict(load_policy())
        ancien['budget'] = {**ancien['budget'], 'llm_eur_per_1k_tokens': 0.004}
        self.conn.execute(
            'INSERT INTO policy_snapshots(content_hash, content_json,'
            " applied_by, active_from) VALUES('h3',?,'owner','t')",
            (json.dumps(ancien),),
        )
        live = latest_policy(self.conn)
        self.assertEqual(live['budget']['llm_daily_eur'], 5.0)
        self.assertEqual(live['budget']['eur_per_usd'], 0.9)


if __name__ == '__main__':
    unittest.main()
