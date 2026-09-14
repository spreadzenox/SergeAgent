#!/usr/bin/env python3
"""MC : POST /owner/api/coupe + projecteur En direct."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import (  # noqa: E402
    heartbeat_marche,
    kinds_interrompus,
)
from serge.db.store import open_db  # noqa: E402
from serge.etapes import etats_etapes  # noqa: E402
from serge.mc.proj_coupes import project_coupes  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class McCoupeApiTests(McServerCase):
    def test_couper_serge_et_remettre(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'serge', 'marche': False, 'decision_id': 'dec-s'},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body.decode('utf-8'))['marche'])
        conn = open_db(self.db_path)
        self.assertFalse(heartbeat_marche(conn))
        conn.close()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'serge', 'marche': True},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body.decode('utf-8'))['marche'])

    def test_couper_kind(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'kind', 'id': 'email.send', 'marche': False},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body.decode('utf-8'))['marche'])
        conn = open_db(self.db_path)
        self.assertIn('email.send', kinds_interrompus(conn))
        conn.close()

    def test_couper_etape_via_coupe(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'etape', 'id': 'caisse', 'marche': False},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body.decode('utf-8'))['marche'])
        conn = open_db(self.db_path)
        self.assertFalse(etats_etapes(conn)['caisse']['marche'])
        conn.close()

    def test_cible_inconnue_400(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'nuage', 'marche': False},
            cookie,
        )
        self.assertEqual(status, 400)
        self.assertIn('Cible', body.decode('utf-8'))

    def test_kind_inconnu_404(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/coupe',
            {'cible': 'kind', 'id': 'nexiste.pas', 'marche': False},
            cookie,
        )
        self.assertEqual(status, 404)

    def test_sans_auth_refuse(self) -> None:
        status, _, _ = self._api_post(
            '/owner/api/coupe',
            {'cible': 'serge', 'marche': False},
        )
        self.assertEqual(status, 401)


class ProjCoupesTests(unittest.TestCase):
    def test_payload_porte_titres(self) -> None:
        import sqlite3

        from serge.db.boot import init_schema

        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        data = project_coupes(conn, {}, '2026-09-14T12:00:00+00:00')
        self.assertTrue(data['serge'])
        self.assertEqual(data['etapes'][0]['id'], 'pre_prospection')
        self.assertIn('Pré-prospection', data['etapes'][0]['titre'])
        mail = next(k for k in data['kinds'] if k['id'] == 'email.send')
        self.assertIn('e-mail', mail['titre'])
        conn.close()


if __name__ == '__main__':
    unittest.main()
