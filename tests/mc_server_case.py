#!/usr/bin/env python3
"""Socle E2E MC : serveur HTTP réel sur port auto (partagé lots 0+)."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.mc.auth import RateLimiter  # noqa: E402
from serge.mc.server import McConfig, create_server  # noqa: E402


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class McServerCase(unittest.TestCase):
    """Serveur MC réel (thread, port auto, DB tmp) + client sans redirect."""

    TOKEN = 'tok-owner-9'

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-mc-')
        self.addCleanup(self.tmp.cleanup)
        self.db_path = Path(self.tmp.name) / 'mc.db'
        conn = open_db(self.db_path)
        conn.close()
        config = McConfig(
            db_path=self.db_path,
            owner_token=self.TOKEN,
            static_dir=ROOT / 'serge/mc/static',
            templates_dir=ROOT / 'serge/mc/templates',
            limiter=RateLimiter(),
        )
        self.server = create_server(config)
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.addCleanup(self._shutdown)
        port = self.server.server_address[1]
        self.port = port
        self.base = f'http://127.0.0.1:{port}'
        self.opener = urllib.request.build_opener(_NoRedirect)

    def _shutdown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def _request(self, method, path, body=None, headers=None):
        req = urllib.request.Request(
            self.base + path, data=body, headers=headers or {}, method=method
        )
        try:
            with self.opener.open(req, timeout=5) as resp:
                heads = {k.lower(): v for k, v in resp.headers.items()}
                return resp.status, heads, resp.read()
        except urllib.error.HTTPError as exc:
            heads = {k.lower(): v for k, v in exc.headers.items()}
            return exc.code, heads, exc.read()

    def _cookie(self, headers) -> str:
        for key, value in headers.items():
            if key.lower() == 'set-cookie' and 'serge_mc=' in value:
                return value.split(';', 1)[0].strip()
        return ''

    def _login(self, token=TOKEN):
        body = urllib.parse.urlencode({'token': token}).encode()
        return self._request(
            'POST',
            '/owner/login',
            body,
            {'Content-Type': 'application/x-www-form-urlencoded'},
        )

    def _auth_cookie(self) -> str:
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        return self._cookie(headers)

    def _api_post(self, chemin, charge, cookie=None):
        headers = {'Content-Type': 'application/json'}
        if cookie:
            headers['Cookie'] = cookie
        if isinstance(charge, str):
            corps = charge.encode('utf-8')
        else:
            corps = json.dumps(charge).encode('utf-8')
        return self._request('POST', chemin, corps, headers)


def browser_ok() -> bool:
    """Chromium pilotable ? (skip gracieux sinon)."""
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


class McBrowserCase(McServerCase):
    """McServerCase + Chromium partagé (classe) + helpers front."""

    @classmethod
    def setUpClass(cls) -> None:
        if not browser_ok():
            raise unittest.SkipTest('navigateur indisponible')
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

    def _wait_for(
        self, page, expression: str, timeout_s: float = 10.0
    ) -> None:
        """Polling via evaluate (wait_for_function string = bloqué CSP)."""
        deadline = time.monotonic() + timeout_s
        while True:
            if page.evaluate(expression):
                return
            if time.monotonic() > deadline:
                raise AssertionError(f'timeout: {expression}')
            time.sleep(0.1)
