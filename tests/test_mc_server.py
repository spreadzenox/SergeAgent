#!/usr/bin/env python3
"""MC serveur E2E : santé, statiques, login/logout, garde /owner, CSP."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McServerCase  # noqa: E402


class McServerTests(McServerCase):
    def test_healthz_robots_favicon(self) -> None:
        status, _, body = self._request('GET', '/healthz')
        self.assertEqual((status, body), (200, b'{"status":"ok"}'))
        status, _, body = self._request('GET', '/robots.txt')
        self.assertEqual(status, 200)
        self.assertIn(b'Disallow: /owner/', body)
        status, _, _ = self._request('GET', '/favicon.ico')
        self.assertEqual(status, 204)

    def test_statiques_et_traversal(self) -> None:
        status, headers, body = self._request('GET', '/static/mc/app.js')
        self.assertEqual(status, 200)
        self.assertIn('javascript', headers.get('content-type', ''))
        self.assertTrue(body)
        status, _, _ = self._request('GET', '/static/mc/../../x')
        self.assertEqual(status, 404)
        status, _, _ = self._request('GET', '/static/mc/%2e%2e/x')
        self.assertEqual(status, 404)
        status, _, _ = self._request('GET', '/static/mc/app.py')
        self.assertEqual(status, 404)

    def test_login_cycle_complet(self) -> None:
        status, _, body = self._request('GET', '/owner/login')
        self.assertEqual(status, 200)
        self.assertIn(b'<form', body)
        status, headers, _ = self._login('mauvais')
        self.assertEqual(status, 401)
        self.assertEqual(self._cookie(headers), '')
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        cookie = self._cookie(headers)
        self.assertTrue(cookie.startswith('serge_mc='))
        conn = sqlite3.connect(self.db_path)
        try:
            count = conn.execute(
                'SELECT COUNT(*) FROM mc_sessions'
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(count, 1)
        status, _, body = self._request(
            'GET', '/owner', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 200)
        self.assertIn(b'Mission Control', body)
        status, _, _ = self._request(
            'POST', '/owner/logout', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 302)
        status, _, _ = self._request(
            'GET', '/owner', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 302)

    def test_owner_sans_auth_redirige(self) -> None:
        status, headers, _ = self._request('GET', '/owner')
        self.assertEqual(status, 302)
        self.assertEqual(headers.get('location'), '/owner/login')

    def test_rate_limit_login(self) -> None:
        for _ in range(10):
            status, _, _ = self._login('mauvais')
            self.assertEqual(status, 401)
        status, _, body = self._login('mauvais')
        self.assertEqual(status, 429)
        self.assertIn('Trop d’essais', body.decode('utf-8'))

    def test_404_francaise(self) -> None:
        status, headers, body = self._request('GET', '/nope')
        self.assertEqual(status, 404)
        self.assertIn('text/html', headers.get('content-type', ''))
        self.assertIn('introuvable', body.decode('utf-8'))

    def test_csp_sans_unsafe(self) -> None:
        for path in ('/owner/login', '/healthz'):
            _, headers, _ = self._request('GET', path)
            csp = headers.get('content-security-policy', '')
            self.assertIn("default-src 'self'", csp)
            self.assertNotIn('unsafe-inline', csp)
            self.assertNotIn('unsafe-eval', csp)


if __name__ == '__main__':
    unittest.main()
