#!/usr/bin/env python3
"""Projecteurs P6 Économie : tests unitaires et goldens."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_economy import (  # noqa: E402
    project_audit_reponses,
    project_couts_cognitifs,
    project_entonnoir,
    project_transactions_subscriptions,
)

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {'budget': {'llm_eur_per_1k_tokens': 0.005}}


class ProjEconomyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn

        conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Agence Alpha', 'ACTIVE', '2026-09-01T10:00:00+00:00', 't')"
        )
        conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state, n_target, created_at, updated_at)'
            " VALUES('c1', 'v1', 'named', 'email', 'RUNNING', 10, '2026-09-02T10:00:00+00:00', 't')"
        )
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, created_at, updated_at)'
            " VALUES('ct1', 'v1', 'Alice', 'alice@test.com', 't', 't')"
        )
        conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel, status, cost_eur, idempotency_key, created_at, updated_at)'
            " VALUES('t1', 'c1', 'ct1', 'email', 'sent', 0.02, 'k1', '2026-09-03T10:00:00+00:00', 't')"
        )
        conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur, currency, intent_id, status, created_at, updated_at)'
            " VALUES('tx1', 'v1', 'invoice', 100.0, 'EUR', 'in_1', 'paid', '2026-09-04T10:00:00+00:00', 't')"
        )
        conn.execute(
            'INSERT INTO subscriptions(id, venture_id, provider, amount_eur, period, status, renews_at, created_at, updated_at)'
            " VALUES('sub1', 'v1', 'stripe', 49.0, 'monthly', 'active', '2026-10-04T10:00:00+00:00', 't', 't')"
        )
        conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out, latency_ms, verdict, created_at)'
            " VALUES('qualify', 'T1', 'nemo', 1000, 1000, 50, 'ok', '2026-09-05T10:00:00+00:00')"
        )
        conn.execute(
            'INSERT INTO artifacts(id, venture_id, kind, version, path_or_url, created_at)'
            " VALUES('art1', 'v1', 'landing', 1, '/tmp/landing', '2026-09-06T10:00:00+00:00')"
        )
        conn.commit()

    def test_entonnoir_golden(self) -> None:
        data = project_entonnoir(self.conn, POLICY, NOW)
        self.assertEqual(len(data['ventures']), 1)
        v = data['ventures'][0]
        self.assertEqual(v['id'], 'v1')
        self.assertEqual(v['u1'], 1)
        self.assertEqual(v['paid_eur'], 100.0)
        self.assertEqual(data['totaux']['u1'], 1)
        self.assertEqual(data['totaux']['paid_eur'], 100.0)

    def test_transactions_subscriptions_golden(self) -> None:
        data = project_transactions_subscriptions(self.conn, POLICY, NOW)
        self.assertEqual(len(data['transactions']), 1)
        self.assertEqual(data['transactions'][0]['id'], 'tx1')
        self.assertEqual(len(data['subscriptions']), 1)
        self.assertEqual(data['mrr_eur'], 49.0)

    def test_couts_cognitifs_golden(self) -> None:
        data = project_couts_cognitifs(self.conn, POLICY, NOW)
        self.assertEqual(data['total_tokens'], 2000)
        self.assertEqual(
            data['total_cost_eur'], 0.01
        )  # 2000 / 1000 * 0.005 = 0.01
        self.assertEqual(data['total_revenue_eur'], 100.0)
        self.assertEqual(data['tokens_par_euro'], 20.0)  # 2000 / 100 = 20.0

    def test_audit_reponses_golden(self) -> None:
        data = project_audit_reponses(self.conn, POLICY, NOW)
        self.assertEqual(len(data['reponses']), 1)
        self.assertEqual(data['reponses'][0]['contact'], 'Alice')
        self.assertEqual(len(data['dette_builder']), 1)
        self.assertEqual(data['dette_builder'][0]['kind'], 'landing')


if __name__ == '__main__':
    unittest.main()
