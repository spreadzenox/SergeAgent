#!/usr/bin/env python3
"""MC P7 Voix : registre + rendu pont / journal / qualité."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class VoiceRegistryTests(unittest.TestCase):
    def test_registre_p7(self) -> None:
        sections = PAGE_SECTIONS['p7']
        self.assertEqual(
            sections,
            ['meta', 'bridge_statut', 'cdr_appels', 'journal_voix'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('cdr_appels', SLOW_SECTIONS)
        self.assertIn('bridge_statut', SLOW_SECTIONS)
        self.assertIn('journal_voix', SLOW_SECTIONS)


class McVoiceTests(McBrowserCase):
    def _page_voice(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/voice')
        from playwright.sync_api import expect

        expect(page.locator('#voice-bridge-info')).to_contain_text(
            'Pont', timeout=10000
        )
        return page

    def test_page_voice_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_voice()
        expect(page.locator('[data-section="bridge_statut"]')).to_contain_text(
            'Pont'
        )
        # Les journaux du serveur : un bloc par source, même illisible.
        journaux = page.locator('[data-section="journal_voix"]')
        expect(journaux).to_contain_text('Pont vocal')
        expect(journaux).to_contain_text('Asterisk, fichier messages')
