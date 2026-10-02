#!/usr/bin/env python3
"""MC P5 Politique : registre + rendu sections + testing froid + snapshots + trust."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from serge.policy import load_policy  # noqa: E402
from serge.policy_snapshots import snapshot_policy  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class PolicyRegistryTests(unittest.TestCase):
    def test_registre_p5(self) -> None:
        sections = PAGE_SECTIONS['p5']
        self.assertEqual(
            sections,
            [
                'meta',
                'politique_active',
                'reglages',
                'testing_froid',
            ],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('politique_active', SLOW_SECTIONS)
        self.assertIn('testing_froid', SLOW_SECTIONS)


class McPolicyTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            pol = load_policy()
            # Un ancien snapshot garde un réglage retiré (Q68) : la page ne
            # doit plus l'afficher.
            pol['quotas']['llm_outil_tours_max'] = 12
            snapshot_policy(conn, pol, applied_by='owner_init')
            conn.commit()
        finally:
            conn.close()

    def _page_policy(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/policy')
        page.locator('[data-section="politique_active"]').wait_for(
            timeout=10000
        )
        return page

    def test_page_policy_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        expect(
            page.locator('[data-section="politique_active"]')
        ).to_contain_text('Argent')
        expect(
            page.locator('[data-section="politique_active"]')
        ).to_contain_text('Plafond du mois')
        expect(
            page.locator('[data-section="politique_active"]')
        ).not_to_contain_text('outil_tours')
        expect(page.locator('#testing-lock-status')).to_contain_text(
            'Aucun essai en cours'
        )
        # Retirés (Q68) : rien ne s'en servait.
        expect(
            page.locator('[data-section="trust_candidates"]')
        ).to_have_count(0)
        expect(page.locator('[data-action="proposer-policy"]')).to_have_count(
            0
        )

    def test_testing_edit_ui(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        page.locator('[data-section="testing_froid"]').wait_for(timeout=10000)
        page.locator('#testing-lock-status[data-etat]').wait_for(timeout=10000)
        champ = page.locator('input[data-testing="n_smoke_min"]')
        btn = page.locator('button[data-btn="enregistrer-testing"]')
        expect(btn).to_be_enabled()
        champ.click()
        champ.fill('42')
        expect(champ).to_have_value('42')
        with page.expect_response(
            lambda resp: (
                '/owner/api/policy/testing' in resp.url
                and resp.request.method == 'POST'
            ),
            timeout=10000,
        ) as pending:
            btn.click()
        self.assertEqual(pending.value.status, 200)
        expect(page.locator('.toast-succes').last).to_contain_text(
            'Taille des essais mise à jour.', timeout=10000
        )
