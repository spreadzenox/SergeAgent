#!/usr/bin/env python3
"""MC P5 Politique : registre + rendu sections + testing froid + snapshots + trust."""

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
                'policy_snapshots',
                'testing_froid',
                'trust_candidates',
            ],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('politique_active', SLOW_SECTIONS)
        self.assertIn('testing_froid', SLOW_SECTIONS)
        self.assertIn('policy_snapshots', SLOW_SECTIONS)
        self.assertIn('trust_candidates', SLOW_SECTIONS)


class McPolicyTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            iso = datetime.now(UTC).isoformat()
            pol = load_policy()
            snapshot_policy(conn, pol, applied_by='owner_init')

            conn.execute(
                'INSERT INTO tickets(id, type, title, state, created_at, updated_at)'
                " VALUES('t_veto', 'VETO_AMONT', 'Prix', 'APPROVED', ?, ?)",
                (iso, iso),
            )
            for _ in range(22):
                conn.execute(
                    'INSERT INTO ticket_events(ticket_id, ts, actor, kind)'
                    ' VALUES("t_veto", ?, "owner", "transition.approved")',
                    (iso,),
                )
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
        expect(page.locator('#testing-lock-status')).to_contain_text(
            'Aucun essai en cours'
        )
        expect(
            page.locator('[data-section="policy_snapshots"]')
        ).to_contain_text('Version')
        expect(
            page.locator('[data-section="trust_candidates"]')
        ).to_contain_text('Veto amont')

    def test_testing_edit_ui(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        btn = page.locator('button[data-btn="enregistrer-testing"]')
        expect(btn).to_be_enabled()
        page.locator('input[data-testing="n_smoke_min"]').fill('42')
        btn.click()
        expect(page.locator('.toast-succes').last).to_contain_text(
            'Taille des essais mise à jour.'
        )

    def test_proposer_policy_ui(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        page.locator('button[data-action="proposer-policy"]').click()
        modale = page.locator('.modale')
        modale.locator('input[name="titre"]').fill('Hausse budget LLM')
        modale.locator('input[name="diff"]').fill('llm_daily_eur: 5 -> 15')
        modale.get_by_role('button', name='Créer la question').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Question Policy'
        )
