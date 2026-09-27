#!/usr/bin/env python3
"""MC : POST /owner/api/coupe (Serge, étape, file, invocation) + boutons."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import heartbeat_marche  # noqa: E402
from serge.db.store import open_db  # noqa: E402
from serge.etapes import etats_etapes  # noqa: E402
from serge.mc.proj_coupes import project_coupes  # noqa: E402
from tests.mc_server_case import McBrowserCase, McServerCase  # noqa: E402
from tests.taches_fixtures import invocations  # noqa: E402


def _avec_une_invocation(db_path: Path) -> None:
    conn = open_db(db_path)
    invocations(conn, ('envoyer', 'Envoyer un e-mail', 'prospection_light'))
    conn.commit()
    conn.close()


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

    def test_couper_une_invocation_et_une_file(self) -> None:
        _avec_une_invocation(self.db_path)
        cookie = self._auth_cookie()
        for cible, ident, table in (
            ('invocation', 'envoyer', 'invocations'),
            ('file', 'works', 'queues'),
        ):
            status, _, body = self._api_post(
                '/owner/api/coupe',
                {'cible': cible, 'id': ident, 'marche': False},
                cookie,
            )
            self.assertEqual(status, 200)
            self.assertFalse(json.loads(body.decode('utf-8'))['marche'])
            conn = open_db(self.db_path)
            enabled = conn.execute(
                f'SELECT enabled FROM {table} WHERE id=?', (ident,)
            ).fetchone()[0]
            conn.close()
            self.assertEqual(enabled, 0)

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

    def test_invocation_inconnue_404(self) -> None:
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/coupe',
            {'cible': 'invocation', 'id': 'nexiste_pas', 'marche': False},
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
        invocations(
            conn, ('envoyer', 'Envoyer un e-mail', 'prospection_light')
        )
        data = project_coupes(conn, {}, '2026-09-14T12:00:00+00:00')
        self.assertTrue(data['serge'])
        self.assertEqual(data['etapes'][0]['id'], 'pre_prospection')
        self.assertIn('Pré-prospection', data['etapes'][0]['titre'])
        self.assertIn('Travaux', data['files'][1]['titre'])
        self.assertEqual(
            data['invocations'],
            [
                {
                    'id': 'envoyer',
                    'titre': 'Envoyer un e-mail',
                    'marche': True,
                    'etape_id': 'prospection_light',
                }
            ],
        )
        conn.close()


class McCoupeFrontTests(McBrowserCase):
    def test_bouton_serge_en_haut(self) -> None:
        from playwright.sync_api import expect

        _avec_une_invocation(self.db_path)
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/live')
        page.locator('[data-section="coupes"]').wait_for(timeout=10000)
        btn = page.locator('.btn-kill-serge')
        expect(btn).to_be_visible()
        expect(btn).to_have_text('Arrêter Serge')
        etapes = page.locator('[data-coupes="etapes"] .btn-kill')
        self.assertGreaterEqual(etapes.count(), 8)
        expect(page.locator('[data-coupes="files"] .btn-kill')).to_have_count(
            2
        )
        expect(
            page.locator('[data-coupes="invocations"] .btn-kill')
        ).to_have_text(['Couper Envoyer un e-mail'])
        btn.click()
        expect(btn).to_have_text('Remettre Serge en marche', timeout=10000)
        expect(page.locator('#live-headline')).to_contain_text('arrêté')


if __name__ == '__main__':
    unittest.main()
