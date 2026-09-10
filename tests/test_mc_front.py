#!/usr/bin/env python3
"""MC front E2E navigateur (skip gracieux si Chromium indisponible)."""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McServerCase  # noqa: E402


def _browser_ok() -> bool:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    try:
        with sync_playwright() as handle:
            browser = handle.chromium.launch(timeout=15000)
            browser.close()
        return True
    except Exception:
        return False


def _wait_for(page, expression: str, timeout_s: float = 10.0) -> None:
    """Polling via evaluate (wait_for_function string = eval = bloqué CSP)."""
    deadline = time.monotonic() + timeout_s
    while True:
        if page.evaluate(expression):
            return
        if time.monotonic() > deadline:
            raise AssertionError(f'timeout: {expression}')
        time.sleep(0.1)


class McFrontTests(McServerCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not _browser_ok():
            raise unittest.SkipTest(
                'navigateur indisponible (playwright install-deps ?)'
            )
        from playwright.sync_api import sync_playwright

        cls._pw = sync_playwright().start()
        cls._browser = cls._pw.chromium.launch()
        cls.addClassCleanup(cls._pw.stop)
        cls.addClassCleanup(cls._browser.close)

    def _auth_context(self):
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        cookie = self._cookie(headers).split('=', 1)[1]
        ctx = self._browser.new_context()
        self.addCleanup(ctx.close)
        ctx.add_cookies(
            [{'name': 'serge_mc', 'value': cookie, 'url': self.base}]
        )
        return ctx

    def _watch_errors(self, page) -> list:
        errors: list = []
        page.on('pageerror', lambda err: errors.append(err))
        self.addCleanup(lambda: self.assertEqual(errors, []))
        return errors

    def test_page_affiche_version_boot(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        page.get_by_text('MC v1 — miroir temps réel.').wait_for(timeout=10000)

    def test_snapshot_sans_stream(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner?snapshot=1')
        _wait_for(page, "window.__MC && window.__MC.stats.mode === 'snapshot'")
        page.get_by_text('MC v1').wait_for(timeout=10000)

    def test_tick_identique_skippe(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        _wait_for(page, 'window.__MC && window.__MC.stats.applied >= 1')
        _wait_for(page, 'window.__MC && window.__MC.stats.skipped >= 1')


if __name__ == '__main__':
    unittest.main()
