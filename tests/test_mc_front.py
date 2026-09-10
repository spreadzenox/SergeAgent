#!/usr/bin/env python3
"""MC front E2E navigateur (skip gracieux si Chromium indisponible)."""

from __future__ import annotations

import sys
import time
import unittest
from datetime import UTC, datetime, timedelta
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

    def test_page_live_etats_vides(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        for text in (
            'Rien en cours',
            'Aucun urgent',
            'File vide',
            'Aucune activité',
            'Budgets du jour',
        ):
            expect(page.locator('#page')).to_contain_text(text)

    def test_snapshot_sans_stream(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner?snapshot=1')
        _wait_for(page, "window.__MC && window.__MC.stats.mode === 'snapshot'")
        page.get_by_text('File vide').wait_for(timeout=10000)

    def test_tick_identique_skippe(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        _wait_for(page, 'window.__MC && window.__MC.stats.applied >= 1')
        _wait_for(page, 'window.__MC && window.__MC.stats.skipped >= 1')

    def test_sidebar_navigation(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        links = page.locator('.barre-laterale nav a')
        self.assertEqual(links.count(), 9)
        self.assertEqual(links.nth(1).text_content().strip(), 'Système')
        links.nth(1).click()
        page.get_by_text('Cette page arrive dans un prochain lot.').wait_for(
            timeout=5000
        )
        self.assertEqual(page.evaluate('window.__MC.stats.page'), 'p1')
        active = page.locator('.barre-laterale a.actif')
        self.assertEqual(active.count(), 1)
        self.assertEqual(active.first.text_content().strip(), 'Système')
        links.nth(0).click()
        page.get_by_text('File vide').wait_for(timeout=5000)
        self.assertEqual(page.evaluate('window.__MC.stats.page'), 'p0')

    def test_hash_inconnu_retombe_live(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/nope')
        page.get_by_text('File vide').wait_for(timeout=5000)
        self.assertEqual(page.evaluate('location.hash'), '#/live')

    def test_page_live_donnees(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        now = datetime.now(UTC)
        iso = now.isoformat()
        soon = (now + timedelta(minutes=5)).isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, email,'
                " created_at, updated_at) VALUES('p1','v1','Ada',"
                "'ada@x.io',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO work_items(id, kind, venture_id, status,'
                ' priority, idempotency_key, created_at, updated_at)'
                " VALUES('w1','email.send','v1','RUNNING',0,'k1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, expiry_at,'
                " created_at, updated_at) VALUES('t1','GUICHET','Captcha',"
                "'OPEN',?,?,?)",
                (soon, iso, iso),
            )
            conn.execute(
                'INSERT INTO touches(id, campaign_id, contact_id, channel,'
                ' status, idempotency_key, created_at, updated_at)'
                " VALUES('t1','c1','p1','email','sent','k-t1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('classify','T1','m',2000,1000,10,'ok',?)",
                (iso,),
            )
            conn.commit()
        finally:
            conn.close()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        for text in (
            'email.send',
            'Captcha',
            'Guichet',
            'Ada',
            '3000 jetons',
        ):
            expect(page.locator('#page')).to_contain_text(text)

    def test_composants_hud(self) -> None:
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner')
        result = page.evaluate("""(async () => {
          const ui = await import('/static/mc/components.js');
          const out = {};
          const shown = ui.toast(document.body, 'Enregistré', 'succes');
          out.toast = shown.className;
          const gauge = ui.createGauge();
          document.body.append(gauge);
          ui.updateGauge(gauge, 0.5, 'alerte');
          out.gauge = gauge.querySelector('span').style.width;
          out.gaugeLevel = gauge.className;
          const spark = ui.sparkline([1, 2, 3]);
          out.spark = spark.tagName.toLowerCase() + ':'
            + spark.querySelector('polyline').getAttribute('points')
              .split(' ').length;
          const done = ui.confirmModal(document.body, {
            title: 'T', message: 'M',
          });
          document.querySelector('.fond-modale button').click();
          out.modal = await done;
          const close = ui.openDrawer(
            document.body, 'Détails', document.createElement('div')
          );
          await new Promise((r) => requestAnimationFrame(() => r()));
          out.drawer = !!document.querySelector('.drawer.ouvert');
          close();
          out.drawerClosed = !document.body.contains(
            document.querySelector('.drawer')
          );
          return out;
        })()""")
        self.assertEqual(result['toast'], 'toast toast-succes')
        self.assertEqual(result['gauge'], '50%')
        self.assertIn('alerte', result['gaugeLevel'])
        self.assertEqual(result['spark'], 'svg:3')
        self.assertTrue(result['modal'])
        self.assertTrue(result['drawer'])
        self.assertTrue(result['drawerClosed'])


if __name__ == '__main__':
    unittest.main()
