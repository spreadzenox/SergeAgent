#!/usr/bin/env python3
"""MC P1 Système : registre sections + page îlots (rendu, clic, fuite)."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class SystemRegistryTests(unittest.TestCase):
    def test_registre_p1(self) -> None:
        sections = PAGE_SECTIONS['p1']
        self.assertEqual(
            sections,
            ['meta', 'ilots', 'scheduler', 'campagnes', 'population', 'email'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('population', SLOW_SECTIONS)


class McSystemTests(McBrowserCase):
    def _fixtures(self) -> None:
        import sqlite3

        now = datetime.now(UTC)
        iso = now.isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO ventures(id, lifecycle, schedulable,'
                " created_at, updated_at) VALUES('v1','SMOKE_RUNNING',"
                '1,?,?)',
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO ventures(id, lifecycle, schedulable,'
                " created_at, updated_at) VALUES('v2','CANDIDATE',0,?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, email,'
                ' regime, funnel_state, created_at, updated_at)'
                " VALUES('p1','v1','Ada','ada@x.io','OUTBOUND',"
                "'CONTACTING',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, email,'
                ' regime, funnel_state, created_at, updated_at)'
                " VALUES('p2','v1','Bob','bob@x.io','OUTBOUND','NEW',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel,'
                ' state, n_target, created_at, updated_at)'
                " VALUES('c1','v1','named','email','RUNNING',10,?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO touches(id, campaign_id, contact_id, channel,'
                ' status, idempotency_key, created_at, updated_at)'
                " VALUES('t1','c1','','email','sent','k-t1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
                ' intent_id, status, created_at, updated_at)'
                " VALUES('x1','v1','invoice',50.0,'in-1','overdue',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO work_items(id, kind, venture_id, status,'
                ' priority, idempotency_key, created_at, updated_at)'
                " VALUES('w1','email.send','v1','READY',0,'k-w1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO accounts_standing(id, venue, handle,'
                ' cooldown_until, updated_at) VALUES'
                "('s1','gmail','a@x.io',?,?)",
                (
                    (now + timedelta(hours=3)).isoformat(),  # → 'dans 2 h'
                    iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _page_home(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/system')
        page.wait_for_url('**/owner#/live', timeout=10000)
        page.locator('.noeud').first.wait_for(timeout=10000)
        return page

    def test_system_redirige_live(self) -> None:
        from playwright.sync_api import expect

        page = self._page_home()
        expect(page.locator('[data-section="graphe"]')).to_be_visible()
        expect(page.get_by_text('Comment Serge gagne de l’argent')).to_be_visible()
        self.assertGreaterEqual(page.locator('.noeud').count(), 7)

    def test_pas_de_fuite_boucle_ilots(self) -> None:
        page = self._page_home()
        compte = (
            "(async () => (await import('/static/mc/hud.js')).hudActives())()"
        )
        self.assertEqual(page.evaluate(compte), 1)
        liens = page.locator('.barre-laterale nav a')
        liens.nth(7).click()
        page.locator('[data-section="charte_metriques"]').wait_for(
            timeout=10000
        )
        self.assertEqual(page.evaluate(compte), 0)
        liens.nth(0).click()
        page.locator('.noeud').first.wait_for(timeout=10000)
        self.assertEqual(page.evaluate(compte), 1)

    def test_sections_systeme_donnees(self) -> None:
        from playwright.sync_api import expect

        page = self._page_home()
        expect(page.locator('[data-section="business"]')).to_contain_text(
            'Smoke en cours'
        )
        expect(page.locator('[data-section="business"]')).not_to_contain_text(
            'SMOKE_RUNNING'
        )
        expect(page.locator('#voix-noyau')).not_to_have_text('…')

    def test_sections_vides_gracieuses(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/system')
        page.locator('#live-headline').wait_for(timeout=10000)
        expect(page.locator('#page')).to_contain_text('Rien en cours')
        expect(page.locator('#page')).to_contain_text('File vide')
