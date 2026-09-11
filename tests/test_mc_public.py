#!/usr/bin/env python3
"""Surface publique P9 : fail-closed, assert_public_safe, tests adversariaux."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_public import (  # noqa: E402
    PublicSafetyViolation,
    assert_public_safe,
    project_public_statut,
)
from tests.mc_server_case import McServerCase  # noqa: E402


class PublicSafetyTests(unittest.TestCase):
    def test_assert_public_safe_passant(self) -> None:
        propre = {
            'statut': 'operationnel',
            'message': 'Tous les systèmes sont opérationnels.',
            'version': 1,
            'liste': ['ok', 'en_ligne'],
        }
        # Ne doit pas lever d'exception
        assert_public_safe(propre)

    def test_assert_public_safe_adversarial_secrets(self) -> None:
        fuzz_secrets = [
            {'cle': 'api_key: sk-1234567890abcdef1234567890'},
            {'token': 'Bearer secret_token_xyz_12345'},
            {
                'data': 'age1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq'
            },
            {'key': '-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...'},
        ]
        for f in fuzz_secrets:
            with (
                self.subTest(fuzz=f),
                self.assertRaises(PublicSafetyViolation),
            ):
                assert_public_safe(f)

    def test_assert_public_safe_adversarial_pii(self) -> None:
        fuzz_pii = [
            {'contact': 'test.user@example.com'},
            {'admin': 'admin@gmail.com'},
            {'telephone': '+33612345678'},
            {'id_interne': 't_1234567890ab'},
            {'worker_id': 'w_abcdef012345'},
        ]
        for f in fuzz_pii:
            with (
                self.subTest(fuzz=f),
                self.assertRaises(PublicSafetyViolation),
            ):
                assert_public_safe(f)


class PublicEndpointTests(McServerCase):
    def test_routes_publiques_sans_auth(self) -> None:
        # / (HTML)
        status, _, body = self._request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('Serge', body.decode('utf-8'))
        self.assertIn('Statut public', body.decode('utf-8'))

        # /robots.txt
        status, _, body_robots = self._request('GET', '/robots.txt')
        self.assertEqual(status, 200)
        self.assertIn('Disallow: /owner/', body_robots.decode('utf-8'))

        # /api/state public
        status, _, body_state = self._request('GET', '/api/state')
        self.assertEqual(status, 200)
        data = json.loads(body_state.decode('utf-8'))
        self.assertEqual(data['statut'], 'operationnel')
        self.assertIn('message', data)

    def test_projection_publique_fail_closed(self) -> None:
        conn = sqlite3.connect(self.db_path)
        try:
            init_schema(conn)
            # Injection de données piégées dans la base
            conn.execute(
                'INSERT INTO contacts(id, venture_id, email, phone, created_at, updated_at)'
                " VALUES('c1', 'v1', 'fuite@prive.com', '+33699887766', 't', 't')"
            )
            conn.commit()
            payload = project_public_statut(conn, {}, '')
            # Aucune fuite ne doit traverser
            assert_public_safe(payload)
            self.assertNotIn('fuite@prive.com', str(payload))
            self.assertNotIn('+33699887766', str(payload))
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
