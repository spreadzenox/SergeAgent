#!/usr/bin/env python3
"""MC P6 Économie : registre + rendu entonnoir + transactions/MRR + coûts + audit."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class EconomyRegistryTests(unittest.TestCase):
    def test_registre_p6(self) -> None:
        sections = PAGE_SECTIONS['p6']
        self.assertEqual(
            sections,
            [
                'meta',
                'entonnoir',
                'transactions_subscriptions',
                'couts_cognitifs',
                'audit_reponses',
            ],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('entonnoir', SLOW_SECTIONS)
        self.assertIn('transactions_subscriptions', SLOW_SECTIONS)
        self.assertIn('couts_cognitifs', SLOW_SECTIONS)
        self.assertIn('audit_reponses', SLOW_SECTIONS)


class McEconomyTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            iso = datetime.now(UTC).isoformat()
            conn.execute(
                'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
                " VALUES('v_eco', 'Projet Beta', 'SMOKE_RUNNING', ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel, state, n_target, created_at, updated_at)'
                " VALUES('c_eco', 'v_eco', 'named', 'email', 'RUNNING', 10, ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, email, created_at, updated_at)'
                " VALUES('ct_eco', 'v_eco', 'Bernard', 'bernard@test.com', ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO touches(id, campaign_id, contact_id, channel, status, cost_eur, idempotency_key, created_at, updated_at)'
                " VALUES('t_eco', 'c_eco', 'ct_eco', 'email', 'sent', 0.05, 'k_eco', ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO transactions(id, venture_id, kind, amount_eur, currency, intent_id, status, created_at, updated_at)'
                " VALUES('tx_eco', 'v_eco', 'invoice', 250.0, 'EUR', 'in_eco', 'paid', ?, ?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO subscriptions(id, venture_id, provider, amount_eur, period, status, renews_at, created_at, updated_at)'
                " VALUES('sub_eco', 'v_eco', 'stripe', 99.0, 'monthly', 'active', ?, ?, ?)",
                (iso, iso, iso),
            )
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out, latency_ms, verdict, created_at)'
                " VALUES('qualify', 'T1', 'nemo', 2000, 500, 45, 'ok', ?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO artifacts(id, venture_id, kind, version, path_or_url, created_at)'
                " VALUES('art_eco', 'v_eco', 'rapport', 1, '/tmp/rapport', ?)",
                (iso,),
            )
            conn.commit()
        finally:
            conn.close()

    def _page_economy(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/economy')
        page.locator('[data-section="entonnoir"]').wait_for(timeout=10000)
        return page

    def test_page_economy_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_economy()
        expect(page.locator('[data-section="entonnoir"]')).to_contain_text(
            'Projet Beta'
        )
        expect(page.locator('[data-section="entonnoir"]')).to_contain_text(
            '250'
        )
        expect(
            page.locator('[data-section="transactions_subscriptions"]')
        ).to_contain_text('MRR récurrent mensuel : 99')
        expect(
            page.locator('[data-section="transactions_subscriptions"]')
        ).to_contain_text('invoice 250')
        expect(
            page.locator('[data-section="couts_cognitifs"]')
        ).to_contain_text('2500 jetons')
        expect(
            page.locator('[data-section="couts_cognitifs"]')
        ).to_contain_text(
            '10 jetons / €'  # 2500 / 250 = 10
        )
        expect(
            page.locator('[data-section="audit_reponses"]')
        ).to_contain_text('Bernard')
        expect(
            page.locator('[data-section="audit_reponses"]')
        ).to_contain_text('Artifact rapport v1')
