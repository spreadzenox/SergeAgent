#!/usr/bin/env python3
"""MC P2 Cerveau : registre sections + page lecture (matrice, listes)."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class MindRegistryTests(unittest.TestCase):
    def test_registre_p2(self) -> None:
        sections = PAGE_SECTIONS['p2']
        self.assertEqual(
            sections,
            ['meta', 'pensees', 'decisions', 'matrice', 'signaux', 'clusters'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('matrice', SLOW_SECTIONS)
        self.assertIn('clusters', SLOW_SECTIONS)


class McMindTests(McBrowserCase):
    def _fixtures(self) -> None:
        import sqlite3

        iso = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('qualify_prospect','T1','nemo',1000,500,100,"
                "'ok',?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('qualify_prospect','T1','nemo',2000,1000,200,"
                "'recall',?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO inbound_events(id, contact_id, channel,'
                ' native_type, signal, class, score, received_at)'
                " VALUES('b1','p1','sms','MO','reply','positive',0.9,?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO listen_docs(id, source, title, cluster_id,'
                " fetched_at) VALUES('d1','rss','Bruit prix','cA',?),"
                "('d2','rss','Bug synchro','cA',?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO runtime_flags(name, value, set_by, set_at,'
                " expires_at, reason) VALUES('llm.judge_allocator',"
                "'kill','test',?,'2999-01-01T00:00:00+00:00','x')",
                (iso,),
            )
            conn.commit()
        finally:
            conn.close()

    def _page_cerveau(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/mind')
        page.locator('table.matrice tbody tr').first.wait_for(timeout=10000)
        return page

    def test_page_cerveau_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_cerveau()
        expect(page.locator('table.matrice tbody tr')).to_have_count(29)
        matrice = page.locator('[data-section="matrice"]')
        expect(matrice).to_contain_text('qualify_prospect')
        expect(matrice).to_contain_text('Tué (temporaire)')
        expect(matrice).to_contain_text('En service')
        expect(page.locator('[data-section="pensees"]')).to_contain_text(
            'Aucune pensée pour le moment.'
        )
        decisions = page.locator('[data-section="decisions"]')
        expect(decisions).to_contain_text('qualify_prospect — ok')
        expect(decisions).to_contain_text('recall')
        expect(page.locator('[data-section="signaux"]')).to_contain_text(
            'sms reply (positive)'
        )
        expect(page.locator('[data-section="clusters"]')).to_contain_text(
            'cA — 2 docs'
        )

    def test_page_cerveau_vide(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/mind')
        page.locator('table.matrice tbody tr').first.wait_for(timeout=10000)
        expect(page.locator('table.matrice tbody tr')).to_have_count(29)
        expect(page.locator('[data-section="matrice"]')).to_contain_text(
            'En service'
        )
        for section, text in (
            ('pensees', 'Aucune pensée pour le moment.'),
            ('decisions', 'Aucune décision récente.'),
            ('signaux', 'Aucun signal récent.'),
            ('clusters', 'Aucun cluster chaud.'),
        ):
            expect(
                page.locator(f'[data-section="{section}"]')
            ).to_contain_text(text)

    def test_fiche_et_kill(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_cerveau()
        page.get_by_role('button', name='qualify_prospect').click()
        tiroir = page.locator('.drawer')
        expect(tiroir).to_contain_text('Point qualify_prospect')
        expect(tiroir).to_contain_text('Garde-fou')
        expect(tiroir).to_contain_text('En service')
        tiroir.get_by_role('button', name='Tuer').click()
        modale = page.locator('.modale')
        modale.locator('input[name="raison"]').fill('dérive vue en matrice')
        modale.get_by_role('button', name='Tuer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'qualify_prospect tué'
        )
        expect(tiroir).to_contain_text('Tué (temporaire)')
        conn = sqlite3.connect(self.db_path)
        try:
            flag = conn.execute(
                'SELECT value FROM runtime_flags'
                " WHERE name='llm.qualify_prospect'"
            ).fetchone()
            ticket = conn.execute(
                "SELECT type FROM tickets WHERE type='POLICY'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(flag[0], 'kill')
        self.assertEqual(ticket[0], 'POLICY')

    def test_unkill(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_cerveau()
        page.get_by_role('button', name='judge_allocator').click()
        tiroir = page.locator('.drawer')
        expect(tiroir).to_contain_text('Tué (temporaire)')
        tiroir.get_by_role('button', name='Relancer').click()
        modale = page.locator('.modale')
        expect(modale).to_contain_text('Relancer judge_allocator ?')
        modale.get_by_role('button', name='Relancer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'judge_allocator relancé'
        )
        expect(tiroir).to_contain_text('En service')
        conn = sqlite3.connect(self.db_path)
        try:
            flag = conn.execute(
                'SELECT value FROM runtime_flags'
                " WHERE name='llm.judge_allocator'"
            ).fetchone()
        finally:
            conn.close()
        self.assertIsNone(flag)
