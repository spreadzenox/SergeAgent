#!/usr/bin/env python3
"""MC : POST /owner/api/etape + projecteur marche."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.etapes import etats_etapes, set_etape_marche  # noqa: E402
from serge.mc.proj_graphe import project_graphe  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class McEtapeTests(McServerCase):
    def test_couper_et_remettre(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/etape',
            {'id': 'ecoute', 'marche': False, 'decision_id': 'dec-1'},
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode('utf-8'))
        self.assertFalse(data['marche'])
        self.assertIn('listen.collect', data['kinds'])
        status, _, body = self._api_post(
            '/owner/api/etape',
            {'id': 'ecoute', 'marche': True},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body.decode('utf-8'))['marche'])

    def test_inconnue_404(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/etape',
            {'id': 'nexistepas', 'marche': False},
            cookie,
        )
        self.assertEqual(status, 404)
        self.assertIn('inconnue', body.decode('utf-8'))


class ProjEtapeMarcheTests(unittest.TestCase):
    def test_epine_porte_marche(self) -> None:
        import sqlite3

        from serge.db.schema import init_schema

        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        set_etape_marche(conn, 'conversation', False)
        data = project_graphe(conn, {}, '2026-09-12T12:00:00+00:00')
        conv = next(n for n in data['epine'] if n['id'] == 'conversation')
        self.assertFalse(conv['marche'])
        self.assertIn('inbound.classify', conv['kinds'])
        self.assertTrue(etats_etapes(conn)['ecoute']['marche'])
        conn.close()


if __name__ == '__main__':
    unittest.main()
