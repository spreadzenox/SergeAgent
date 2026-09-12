#!/usr/bin/env python3
"""MC P14a : palette de commande Ctrl+K (cmdk.js) + tests E2E."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McBrowserCase  # noqa: E402


class CmdkTests(McBrowserCase):
    def test_cmdk_ouverture_navigation_action(self) -> None:
        from playwright.sync_api import expect

        ctx = self._auth_context()
        page = ctx.new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/live')
        page.locator('#live-headline').wait_for(timeout=10000)

        # Pas ouverte par défaut
        expect(page.locator('.cmdk-boite')).to_have_count(0)

        # Raccourci Ctrl+K
        page.keyboard.press('Control+KeyK')
        expect(page.locator('.cmdk-boite')).to_be_visible()
        expect(page.locator('.cmdk-input')).to_be_focused()

        # Filtrage par recherche
        page.locator('.cmdk-input').fill('cerveau')
        items = page.locator('.cmdk-item')
        expect(items).to_contain_text('Cerveau')

        # Touche Entrée pour exécuter la navigation
        page.keyboard.press('Enter')
        expect(page.locator('.cmdk-boite')).to_have_count(0)
        expect(page.locator('.barre-laterale a.actif')).to_have_text('Cerveau')

        # Réouverture et fermeture via Escape
        page.keyboard.press('Control+KeyK')
        expect(page.locator('.cmdk-boite')).to_be_visible()
        page.keyboard.press('Escape')
        expect(page.locator('.cmdk-boite')).to_have_count(0)


if __name__ == '__main__':
    unittest.main()
