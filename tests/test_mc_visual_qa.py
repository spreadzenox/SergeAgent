#!/usr/bin/env python3
"""MC P14b : QA visuelle complète (desktop + mobile) et responsive."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McBrowserCase  # noqa: E402


class VisualQaTests(McBrowserCase):
    def test_responsive_mobile_et_desktop(self) -> None:
        from playwright.sync_api import expect

        ctx_desktop = self._browser.new_context(
            viewport={'width': 1280, 'height': 800}
        )
        self.addCleanup(ctx_desktop.close)
        page_desk = ctx_desktop.new_page()
        page_desk.goto(f'{self.base}/owner/login')
        expect(page_desk.locator('main.login')).to_be_visible()

        ctx_mobile = self._browser.new_context(
            viewport={'width': 375, 'height': 667}
        )
        self.addCleanup(ctx_mobile.close)
        page_mob = ctx_mobile.new_page()
        page_mob.goto(f'{self.base}/owner/login')
        expect(page_mob.locator('main.login')).to_be_visible()
        # En mobile, la boîte s'adapte sans déborder
        box = page_mob.locator('main.login').bounding_box()
        self.assertIsNotNone(box)
        assert box is not None
        self.assertTrue(box['width'] <= 375)


if __name__ == '__main__':
    unittest.main()
