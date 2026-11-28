#!/usr/bin/env python3
"""MC serveur E2E : santé, statiques, login/logout, garde /owner, CSP."""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import sys
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.auth import client_ip  # noqa: E402
from serge.mc.server import main as mc_main  # noqa: E402
from serge.secrets import owner_dashboard_token  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class McServerTests(McServerCase):
    def test_healthz_robots_favicon(self) -> None:
        status, _, body = self._request('GET', '/healthz')
        self.assertEqual((status, body), (200, b'{"status": "ok"}'))
        status, _, body = self._request('GET', '/robots.txt')
        self.assertEqual(status, 200)
        self.assertIn(b'Disallow: /owner/', body)
        status, _, _ = self._request('GET', '/favicon.ico')
        self.assertEqual(status, 204)

    def test_statiques_et_traversal(self) -> None:
        for path, kind in (
            ('/static/mc/app.js', 'javascript'),
            ('/static/mc/store.js', 'javascript'),
            ('/static/mc/sse.js', 'javascript'),
            ('/static/mc/patch.js', 'javascript'),
            ('/static/mc/style.css', 'text/css'),
        ):
            status, headers, body = self._request('GET', path)
            self.assertEqual(status, 200, path)
            self.assertIn(kind, headers.get('content-type', ''), path)
            self.assertTrue(body, path)
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

    def test_la_limite_d_essais_compte_par_visiteur(self) -> None:
        """Derrière Caddy, toute requête arrive de 127.0.0.1 : la limite
        compte l'adresse que Caddy transmet. Dix essais d'un inconnu ne
        ferment pas la porte au propriétaire."""
        self.assertEqual(
            client_ip(
                '127.0.0.1', {'x-forwarded-for': '1.2.3.4, 203.0.113.9'}
            ),
            '203.0.113.9',
        )
        self.assertEqual(
            client_ip('198.51.100.7', {'x-forwarded-for': '203.0.113.9'}),
            '198.51.100.7',
        )
        corps = urllib.parse.urlencode({'token': 'mauvais'}).encode()
        inconnu = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'X-Forwarded-For': '203.0.113.9',
        }
        for _ in range(10):
            status, _, _ = self._request(
                'POST', '/owner/login', corps, inconnu
            )
            self.assertEqual(status, 401)
        status, _, _ = self._request('POST', '/owner/login', corps, inconnu)
        self.assertEqual(status, 429)
        status, _, _ = self._login()
        self.assertEqual(status, 302)

    def test_un_jeton_par_en_tete_a_la_meme_limite(self) -> None:
        """Un jeton envoyé par en-tête puis refusé compte comme un essai :
        après dix refus, l'en-tête n'est plus écouté pendant une minute.
        Une session ouverte n'est pas touchée."""
        cookie = self._auth_cookie()
        chemin = '/owner/api/state?page=p0'
        for _ in range(10):
            status, _, _ = self._request(
                'GET', chemin, headers={'Authorization': 'Bearer faux'}
            )
            self.assertEqual(status, 401)
        bon = {'Authorization': f'Bearer {self.TOKEN}'}
        status, _, _ = self._request('GET', chemin, headers=bon)
        self.assertEqual(status, 401)
        status, _, _ = self._request('GET', chemin, headers={'Cookie': cookie})
        self.assertEqual(status, 200)
        # Un jeton avec un caractère hors ASCII est refusé comme un autre.
        status, _, _ = self._request(
            'GET',
            chemin,
            headers={
                'X-Serge-Owner-Token': 'jetön'.encode().decode('latin-1')
            },
        )
        self.assertEqual(status, 401)

    def test_une_requete_venue_d_un_autre_hote_est_refusee(self) -> None:
        """Une page servie ailleurs (un produit publié sur un sous-domaine,
        par exemple) ne fait rien faire à Mission Control avec la session
        ouverte : ni action, ni connexion. La page de Mission Control, et
        un client sans navigateur, passent."""
        cookie = self._auth_cookie()
        base = {'Content-Type': 'application/json', 'Cookie': cookie}
        ailleurs = (
            {'Origin': 'https://staging-produit.exemple.fr'},
            {'Origin': 'null'},
            {'Sec-Fetch-Site': 'same-site'},
            {'Sec-Fetch-Site': 'cross-site'},
        )
        for entetes in ailleurs:
            status, _, corps = self._request(
                'POST', '/owner/api/coupe', b'{}', {**base, **entetes}
            )
            self.assertEqual(status, 403, entetes)
            self.assertEqual(json.loads(corps)['code'], 'origine')
        status, _, _ = self._request(
            'POST',
            '/owner/login',
            urllib.parse.urlencode({'token': self.TOKEN}).encode(),
            {
                'Content-Type': 'application/x-www-form-urlencoded',
                'Origin': 'https://ailleurs.exemple.fr',
            },
        )
        self.assertEqual(status, 403)
        chez_soi = {
            'Origin': f'http://127.0.0.1:{self.port}',
            'Sec-Fetch-Site': 'same-origin',
        }
        for entetes in (chez_soi, {}):
            status, _, _ = self._request(
                'POST', '/owner/api/coupe', b'{}', {**base, **entetes}
            )
            self.assertNotEqual(status, 403, entetes)

    def test_une_requete_par_connexion(self) -> None:
        """Mission Control ferme la connexion après chaque réponse : le
        corps d'une requête qu'elle n'a pas lu n'est jamais pris pour la
        requête suivante (Caddy réutilise ses connexions)."""
        with socket.create_connection(('127.0.0.1', self.port), 5) as s:
            s.sendall(
                (
                    'POST /inconnue HTTP/1.1\r\n'
                    f'Host: 127.0.0.1:{self.port}\r\n'
                    'Content-Length: 5\r\n\r\nx=un\n'
                ).encode()
            )
            s.settimeout(5)
            recu = b''
            while morceau := s.recv(65536):
                recu += morceau
        tete, _, _ = recu.partition(b'\r\n\r\n')
        self.assertTrue(tete.startswith(b'HTTP/1.1 404'), tete[:40])
        self.assertIn(b'connection: close', tete.lower())
        self.assertEqual(recu.count(b'HTTP/1.1 '), 1)
        status, entetes, _ = self._request('GET', '/healthz')
        self.assertEqual((status, entetes.get('connection')), (200, 'close'))

    def test_le_cookie_ne_repart_pas_en_clair(self) -> None:
        """Derrière Caddy en HTTPS, le cookie de session porte « Secure »."""
        status, entetes, _ = self._request(
            'POST',
            '/owner/login',
            urllib.parse.urlencode({'token': self.TOKEN}).encode(),
            {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Forwarded-Proto': 'https',
            },
        )
        self.assertEqual(status, 302)
        self.assertIn('; Secure', entetes['set-cookie'])
        _, entetes, _ = self._login()
        self.assertNotIn('Secure', entetes['set-cookie'])

    def test_sans_jeton_mission_control_ne_demarre_pas(self) -> None:
        """Pas de jeton de repli : sans fichier de jeton lisible, le
        service s'arrête en le disant, au lieu d'ouvrir avec un jeton connu."""
        vide = Path(self.tmp.name) / 'vide'
        (vide / 'config').mkdir(parents=True)
        instance = vide / 'instance.toml'
        instance.write_text(f'[paths]\nconfig_root = "{vide / "config"}"\n')
        env = {
            'SERGE_SYSTEM_ROOT': str(vide),
            'SERGE_INSTANCE_FILE': str(instance),
        }
        with mock.patch.dict(os.environ, env):
            os.environ.pop('SERGE_MC_TOKEN', None)
            self.assertEqual(owner_dashboard_token(vide), '')
            with (
                mock.patch.object(sys, 'argv', ['mc', '--port', '0']),
                self.assertRaises(SystemExit) as arret,
            ):
                mc_main()
        self.assertIn('jeton du propriétaire absent', str(arret.exception))

    def test_404_francaise(self) -> None:
        status, headers, body = self._request('GET', '/nope')
        self.assertEqual(status, 404)
        self.assertIn('text/html', headers.get('content-type', ''))
        self.assertIn('introuvable', body.decode('utf-8'))

    def test_csp_sans_unsafe(self) -> None:
        status, headers, _ = self._login()
        authed = {'Cookie': self._cookie(headers)}
        for path, heads in (
            ('/owner/login', {}),
            ('/healthz', {}),
            ('/robots.txt', {}),
            ('/favicon.ico', {}),
            ('/owner', authed),
            ('/owner/api/state?page=p0', authed),
            ('/static/mc/app.js', {}),
            ('/nope', {}),
        ):
            _, found, _ = self._request('GET', path, headers=heads)
            csp = found.get('content-security-policy', '')
            self.assertIn("default-src 'self'", csp, path)
            self.assertNotIn('unsafe-inline', csp, path)
            self.assertNotIn('unsafe-eval', csp, path)


if __name__ == '__main__':
    unittest.main()
