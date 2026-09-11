#!/usr/bin/env python3
"""MC P4 Mémoire : registre + rendu 5 couches + recherche FTS (curation en 8d)."""

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
from serge.memory.lessons import add_lesson  # noqa: E402
from serge.memory.search import index_document  # noqa: E402
from serge.memory.summaries import put_summary  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class MemoryRegistryTests(unittest.TestCase):
    def test_registre_p4(self) -> None:
        sections = PAGE_SECTIONS['p4']
        self.assertEqual(
            sections, ['meta', 'couches', 'consolidation', 'requested']
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('couches', SLOW_SECTIONS)
        self.assertIn('consolidation', SLOW_SECTIONS)
        self.assertIn('requested', SLOW_SECTIONS)


class McMemoryTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            iso = datetime.now(UTC).isoformat()
            # C1
            conn.execute(
                'INSERT INTO episode_archives(id, path, period, count, sha256, created_at)'
                " VALUES(1, '/tmp/ep1.tar', '2026-08', 42, 'abcd1234ef5678', ?)",
                (iso,),
            )
            # C2
            conn.execute(
                'INSERT INTO playbooks(id, name, conditions, steps_json, scope, created_at, updated_at)'
                " VALUES('pb1', 'Relance Client', 'apres 3j sans reponse', '[\"email\"]', 'global', ?, ?)",
                (iso, iso),
            )
            # C3
            conn.execute(
                'INSERT INTO pitfalls(id, statement, cost_observed, scope, created_at)'
                " VALUES('pf1', 'Remise sans accord', 'marge', 'global', ?)",
                (iso,),
            )
            # C4
            add_lesson(
                conn, 'Valider le SIRET systématiquement', confidence=0.85
            )

            # C5
            put_summary(conn, 'serge_md', 'Version 1 de base.')
            put_summary(conn, 'serge_md', 'Version 2 mise à jour.')

            # Consolidation
            put_summary(conn, 'consolidation', iso)

            # Requested
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json, created_at, updated_at)'
                " VALUES('req1', 'REQUESTED', 'Filtre NAF', 'OPEN',"
                ' \'{"demande": "Ajouter code NAF", "point_llm": "qualify"}\', ?, ?)',
                (iso, iso),
            )

            # Document FTS
            index_document(
                conn,
                'lesson',
                'les_siret',
                'Document sur le SIRET et les entreprises',
            )
            conn.commit()
        finally:
            conn.close()

    def _page_memory(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/memory')
        page.locator('.memory-tabs').wait_for(timeout=10000)
        return page

    def test_page_memory_rendu_et_onglets(self) -> None:
        from playwright.sync_api import expect

        page = self._page_memory()
        # C1 par défaut
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            '1 archive(s)'
        )

        # C2
        page.locator('button[data-couche="c2"]').click()
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            'Relance Client'
        )

        # C3
        page.locator('button[data-couche="c3"]').click()
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            'Remise sans accord'
        )

        # C4
        page.locator('button[data-couche="c4"]').click()
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            'Valider le SIRET'
        )

        # C5
        page.locator('button[data-couche="c5"]').click()
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            'Version 2 mise à jour.'
        )
        expect(page.locator('[data-couche-vue="contenu"]')).to_contain_text(
            'Version 1 de base.'
        )

        # Consolidation & requested
        expect(page.locator('[data-section="consolidation"]')).to_contain_text(
            'Dernière exécution :'
        )
        expect(page.locator('[data-section="requested"]')).to_contain_text(
            'Filtre NAF'
        )

    def test_recherche_fts_ui(self) -> None:
        from playwright.sync_api import expect

        page = self._page_memory()
        page.locator('input[data-input="recherche"]').fill('SIRET')
        page.locator('button[data-action="lancer-recherche"]').click()
        expect(page.locator('[data-recherche="resultats"]')).to_contain_text(
            'les_siret'
        )
