#!/usr/bin/env python3
"""MC P7 Voix : registre + rendu bridge/CDR/qualité + kill-switch toggle UI."""

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
from serge.voice.quality import record_call_score  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class VoiceRegistryTests(unittest.TestCase):
    def test_registre_p7(self) -> None:
        sections = PAGE_SECTIONS['p7']
        self.assertEqual(
            sections,
            ['meta', 'cdr_appels', 'qualite_voix', 'bridge_statut'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('cdr_appels', SLOW_SECTIONS)
        self.assertIn('qualite_voix', SLOW_SECTIONS)
        self.assertIn('bridge_statut', SLOW_SECTIONS)


class McVoiceTests(McBrowserCase):
    def _fixtures(self) -> None:
        conn = open_db(self.db_path)
        try:
            record_call_score(conn, 'cdr_test_1', 4, ['bruit'], False)
            record_call_score(conn, 'cdr_test_2', 5, [], False)
            conn.commit()
        finally:
            conn.close()

    def _page_voice(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/voice')
        page.locator('[data-section="bridge_statut"]').wait_for(timeout=10000)
        return page

    def test_page_voice_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_voice()
        expect(page.locator('[data-section="bridge_statut"]')).to_contain_text(
            'Kill Switch Voix'
        )
        expect(page.locator('[data-section="qualite_voix"]')).to_contain_text(
            '4.5 / 5'
        )

    def test_toggle_kill_voice_ui(self) -> None:
        from playwright.sync_api import expect

        page = self._page_voice()
        btn = page.locator('button[data-action="toggle-kill-voice"]')
        btn.click()

        modale = page.locator('.modale')
        modale.get_by_role('button', name='Activer').click()

        expect(page.locator('.toast-succes')).to_contain_text(
            'Kill Switch Voix : ACTIVÉ.'
        )
        expect(page.locator('#voice-bridge-info')).to_contain_text('ACTIF')
