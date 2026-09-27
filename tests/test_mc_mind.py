#!/usr/bin/env python3
"""MC P2 Cerveau : sections, invocations en base, allumer et éteindre."""

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
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402


class MindRegistryTests(unittest.TestCase):
    def test_registre_p2(self) -> None:
        sections = PAGE_SECTIONS['p2']
        self.assertEqual(
            sections,
            ['meta', 'pensees', 'decisions', 'matrice', 'signaux'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('matrice', SLOW_SECTIONS)


class McMindTests(McBrowserCase):
    def _fixtures(self) -> None:
        import sqlite3

        iso = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            sans_pipeline_de_depart(conn)
            seed_pipeline(
                conn,
                {
                    'schema_version': 1,
                    'invocations': [
                        {
                            'id': 'classer',
                            'title': 'Classer une réponse',
                            'type': 'llm',
                            'model_tier': 'fast',
                            'step': 'prospection_lourde',
                        },
                        {
                            'id': 'arbitrer',
                            'title': 'Arbitrer',
                            'type': 'llm',
                            'step': 'prospection_lourde',
                            'enabled': False,
                        },
                    ],
                },
            )
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('classer','fast','nemo',1000,500,100,"
                "'ok',?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('classer','fast','nemo',2000,1000,200,"
                "'format_invalide',?)",
                (iso,),
            )
            conn.execute(
                'INSERT INTO inbound_events(id, contact_id, channel,'
                ' native_type, signal, class, score, received_at)'
                " VALUES('b1','p1','sms','MO','reply','positive',0.9,?)",
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

    def _enabled(self, ident: str) -> int:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT enabled FROM invocations WHERE id=?', (ident,)
            ).fetchone()[0]
        finally:
            conn.close()

    def test_page_cerveau_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_cerveau()
        expect(page.locator('table.matrice tbody tr')).to_have_count(2)
        matrice = page.locator('[data-section="matrice"]')
        expect(matrice).to_contain_text('Classer une réponse')
        expect(matrice).to_contain_text('Allumée')
        expect(matrice).to_contain_text('Éteinte')
        expect(page.locator('[data-section="pensees"]')).to_contain_text(
            'Aucune pensée pour le moment.'
        )
        decisions = page.locator('[data-section="decisions"]')
        expect(decisions).to_contain_text('classer — ok')
        expect(decisions).to_contain_text('format_invalide')
        expect(page.locator('[data-section="signaux"]')).to_contain_text(
            'sms reply (positive)'
        )

    def test_page_cerveau_vide(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        conn = sqlite3.connect(self.db_path)
        sans_pipeline_de_depart(conn)
        conn.commit()
        conn.close()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/mind')
        expect(page.locator('[data-section="matrice"]')).to_contain_text(
            'Aucune invocation en base'
        )
        for section, text in (
            ('pensees', 'Aucune pensée pour le moment.'),
            ('decisions', 'Aucune décision récente.'),
            ('signaux', 'Aucun signal récent.'),
        ):
            expect(
                page.locator(f'[data-section="{section}"]')
            ).to_contain_text(text)

    def test_fiche_et_eteindre(self) -> None:
        from playwright.sync_api import expect

        page = self._page_cerveau()
        page.get_by_role('button', name='Classer une réponse').click()
        tiroir = page.locator('.drawer')
        expect(tiroir).to_contain_text('Classer une réponse')
        expect(tiroir).to_contain_text('Allumée')
        tiroir.get_by_role('button', name='Éteindre').click()
        modale = page.locator('.modale')
        modale.get_by_role('button', name='Éteindre').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Classer une réponse éteinte'
        )
        expect(tiroir).to_contain_text('Éteinte')
        self.assertEqual(self._enabled('classer'), 0)

    def test_allumer(self) -> None:
        from playwright.sync_api import expect

        page = self._page_cerveau()
        page.get_by_role('button', name='Arbitrer').click()
        tiroir = page.locator('.drawer')
        expect(tiroir).to_contain_text('Éteinte')
        tiroir.get_by_role('button', name='Allumer').click()
        modale = page.locator('.modale')
        expect(modale).to_contain_text('Allumer Arbitrer ?')
        modale.get_by_role('button', name='Allumer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Arbitrer allumée'
        )
        expect(tiroir).to_contain_text('Allumée')
        self.assertEqual(self._enabled('arbitrer'), 1)
