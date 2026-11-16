#!/usr/bin/env python3
"""L'écran du vrai Chrome dans Mission Control, derrière la connexion (Q97).

Le serveur de Mission Control est réel ; le noVNC du conteneur est un faux
serveur local, qui rend une page ou fait l'écho d'une WebSocket.

Scénarios :
- sans connexion, l'écran mène à la page de connexion ;
- connecté, ``/owner/vrai-chrome`` ouvre noVNC, ses fichiers viennent du
  conteneur, sans les cookies de Mission Control ;
- plusieurs fichiers de suite passent sur la même connexion, comme les
  demande Caddy (une connexion fermée sans le dire donnait des 502) ;
- le flux de l'écran (une WebSocket) passe dans les deux sens ;
- le vrai Chrome éteint : un message clair ;
- la page d'essai du captcha (page Système) se lit sans connexion, et un
  clic sur son bouton montre un code à quatre chiffres.
"""

from __future__ import annotations

import http.client
import socket
import socketserver
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc import ecran_actions  # noqa: E402
from tests.mc_server_case import (  # noqa: E402
    McServerCase,
    _chromium_kwargs,
    browser_ok,
)


class _FauxNoVnc(socketserver.BaseRequestHandler):
    vus: list[str] = []

    def handle(self) -> None:
        tete = b''
        while b'\r\n\r\n' not in tete:
            morceau = self.request.recv(4096)
            if not morceau:
                return
            tete += morceau
        texte = tete.decode('latin-1')
        _FauxNoVnc.vus.append(texte)
        if 'Upgrade: websocket' in texte:
            self.request.sendall(
                b'HTTP/1.1 101 Switching Protocols\r\n'
                b'Upgrade: websocket\r\nConnection: Upgrade\r\n\r\n'
            )
            while donnees := self.request.recv(4096):
                self.request.sendall(donnees)
            return
        self.request.sendall(
            b'HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\npage novnc'
        )


class EcranTests(McServerCase):
    def setUp(self) -> None:
        super().setUp()
        _FauxNoVnc.vus = []
        socketserver.ThreadingTCPServer.allow_reuse_address = True
        self.novnc = socketserver.ThreadingTCPServer(
            ('127.0.0.1', 0), _FauxNoVnc
        )
        self.novnc.daemon_threads = True
        threading.Thread(target=self.novnc.serve_forever, daemon=True).start()
        self.addCleanup(self.novnc.server_close)
        self.addCleanup(self.novnc.shutdown)
        adresse = f'127.0.0.1:{self.novnc.server_address[1]}'
        patch = mock.patch.object(
            ecran_actions, 'adresse_ecran', return_value=adresse
        )
        self.adresse = patch.start()
        self.addCleanup(patch.stop)

    def test_sans_connexion_la_page_de_connexion(self) -> None:
        status, headers, _ = self._request(
            'GET', '/owner/vrai-chrome/vnc.html'
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers['location'], '/owner/login')
        self.assertEqual(_FauxNoVnc.vus, [])

    def test_connecte_les_fichiers_de_novnc(self) -> None:
        cookie = self._auth_cookie()
        status, headers, _ = self._request(
            'GET', '/owner/vrai-chrome', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 302)
        self.assertEqual(headers['location'], ecran_actions.ACCUEIL)
        status, _headers, corps = self._request(
            'GET',
            '/owner/vrai-chrome/vnc.html?autoconnect=1',
            headers={'Cookie': cookie},
        )
        self.assertEqual((status, corps), (200, b'page novnc'))
        requete = _FauxNoVnc.vus[-1]
        self.assertTrue(requete.startswith('GET /vnc.html?autoconnect=1 '))
        self.assertNotIn('serge_mc', requete, 'pas le cookie de MC')

    def test_plusieurs_fichiers_sur_la_meme_connexion(self) -> None:
        """Caddy garde sa connexion à Mission Control d'un fichier à
        l'autre : chaque réponse dit sa taille et laisse la connexion
        ouverte (16 novembre 2026 : un fichier sur dix revenait en 502)."""
        cookie = self._auth_cookie()
        connexion = http.client.HTTPConnection(
            '127.0.0.1', self.port, timeout=5
        )
        self.addCleanup(connexion.close)
        prises = set()
        for fichier in ('vnc.html', 'app/ui.js', 'core/rfb.js'):
            connexion.request(
                'GET',
                f'/owner/vrai-chrome/{fichier}',
                headers={'Cookie': cookie},
            )
            reponse = connexion.getresponse()
            self.assertEqual(
                (reponse.status, reponse.read()), (200, b'page novnc')
            )
            self.assertEqual(reponse.getheader('Content-Length'), '10')
            self.assertFalse(reponse.will_close, 'la connexion reste ouverte')
            prises.add(id(connexion.sock))
        self.assertEqual(len(prises), 1, 'une seule connexion a servi')
        self.assertEqual(len(_FauxNoVnc.vus), 3)

    def test_le_flux_de_l_ecran_passe_dans_les_deux_sens(self) -> None:
        cookie = self._auth_cookie()
        with socket.create_connection(('127.0.0.1', self.port), 5) as s:
            s.sendall(
                (
                    'GET /owner/vrai-chrome/websockify HTTP/1.1\r\n'
                    f'Host: 127.0.0.1:{self.port}\r\nCookie: {cookie}\r\n'
                    'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                    'Sec-WebSocket-Key: dGVzdA==\r\n\r\n'
                ).encode()
            )
            reponse = b''
            while b'\r\n\r\n' not in reponse:
                reponse += s.recv(4096)
            self.assertTrue(reponse.startswith(b'HTTP/1.1 101'))
            s.sendall(b'clic en 120,340')
            self.assertEqual(s.recv(4096), b'clic en 120,340')

    def test_vrai_chrome_eteint(self) -> None:
        cookie = self._auth_cookie()
        self.adresse.return_value = ''
        status, _headers, corps = self._request(
            'GET', '/owner/vrai-chrome/vnc.html', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 503)
        self.assertIn('ne tourne pas', corps.decode('utf-8'))


class PageDEssaiTests(McServerCase):
    @unittest.skipUnless(browser_ok(), 'Chromium indisponible')
    def test_un_clic_montre_un_code(self) -> None:
        from playwright.sync_api import sync_playwright

        status, _headers, _corps = self._request(
            'GET', '/static/essai/captcha.html'
        )
        self.assertEqual(status, 200, 'sans connexion')
        with sync_playwright() as handle:
            navigateur = handle.chromium.launch(**_chromium_kwargs())
            page = navigateur.new_page()
            page.goto(f'{self.base}/static/essai/captcha.html')
            self.assertFalse(page.locator('#resultat').is_visible())
            page.get_by_role('button', name='Je suis un humain').click()
            self.assertIn(
                'Captcha résolu', page.locator('#resultat').inner_text()
            )
            self.assertRegex(page.locator('#code').inner_text(), r'^\d{4}$')
            navigateur.close()


if __name__ == '__main__':
    unittest.main()
