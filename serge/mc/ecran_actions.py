#!/usr/bin/env python3
"""MC : l'écran du vrai Chrome, derrière la connexion (``/owner/vrai-chrome``).

Le conteneur du vrai Chrome sert son écran avec noVNC
(``serge/sandbox/chrome.py``), sur un port du serveur seulement. Mission
Control vérifie la connexion, puis relaie la requête telle quelle : les
fichiers de noVNC, puis le flux de l'écran (une WebSocket). Il ne lit ni ne
change ce qui passe, et ne transmet ni ses cookies ni son jeton.

Exemple : ``/owner/vrai-chrome`` mène à
``/owner/vrai-chrome/vnc.html?autoconnect=1…`` ; les fichiers
``/vnc.html``, ``/app/ui.js``… viennent du conteneur, puis
``/owner/vrai-chrome/websockify`` porte l'écran, la souris et le clavier.
"""

from __future__ import annotations

import socket
import threading
import urllib.parse
from typing import TYPE_CHECKING, Any, Protocol

from serge.sandbox.chrome import adresse_ecran
from serge.sandbox.docker import journal

PREFIXE = '/owner/vrai-chrome'
ACCUEIL = (
    f'{PREFIXE}/vnc.html?autoconnect=1&resize=scale&reconnect=1'
    f'&path={PREFIXE.lstrip("/")}/websockify'
)
# Ce qui reste dans Mission Control : la connexion, et la façon de parler
# au navigateur de l'humain.
_GARDES = frozenset(
    {'host', 'cookie', 'authorization', 'x-serge-owner-token', 'connection'}
)


class _Handler(Protocol):
    path: str
    command: str
    headers: Any
    connection: Any
    rfile: Any
    wfile: Any
    close_connection: bool

    def _is_owner(self) -> bool: ...
    def _send(self, code: int, body: bytes, content_type: str) -> None: ...
    def send_response(self, code: int, message: str | None = None) -> None: ...
    def send_header(self, keyword: str, value: str) -> None: ...
    def end_headers(self) -> None: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


class EcranMixin(_Base):
    """GET /owner/vrai-chrome…"""

    def _vers(self, adresse: str) -> None:
        self.send_response(302)
        self.send_header('Location', adresse)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _ecran(self) -> None:
        if not self._is_owner():
            self._vers('/owner/login')
            return
        parts = urllib.parse.urlsplit(self.path)
        reste = parts.path[len(PREFIXE) :]
        if reste in ('', '/'):
            self._vers(ACCUEIL)
            return
        adresse = adresse_ecran()
        if not adresse:
            self._texte(
                503,
                'Le vrai Chrome ne tourne pas : il démarre quand une'
                ' invocation s’en sert.',
            )
            return
        hote, _, port = adresse.rpartition(':')
        try:
            amont = socket.create_connection((hote, int(port)), timeout=10)
        except (OSError, ValueError) as exc:
            journal(f'écran du vrai Chrome injoignable ({adresse}) : {exc}')
            self._texte(502, f'Écran du vrai Chrome injoignable : {exc}')
            return
        cible = reste + (f'?{parts.query}' if parts.query else '')
        websocket = (self.headers.get('Upgrade') or '').lower() == 'websocket'
        lignes = [f'{self.command} {cible} HTTP/1.1', f'Host: {adresse}']
        lignes += [
            f'{nom}: {valeur}'
            for nom, valeur in self.headers.items()
            if nom.lower() not in _GARDES
        ]
        lignes.append(
            'Connection: Upgrade' if websocket else 'Connection: close'
        )
        amont.sendall(('\r\n'.join(lignes) + '\r\n\r\n').encode('latin-1'))
        amont.settimeout(None)
        self.close_connection = True
        _relayer(self.connection, self.rfile, self.wfile, amont)

    def _texte(self, code: int, texte: str) -> None:
        self.close_connection = True
        self._send(code, texte.encode('utf-8'), 'text/plain; charset=utf-8')


def _relayer(
    client: Any, rfile: Any, wfile: Any, amont: socket.socket
) -> None:
    """Fait passer les octets dans les deux sens jusqu'à ce qu'un côté
    ferme : une page (le conteneur ferme après sa réponse) ou l'écran
    (l'humain ferme l'onglet)."""

    def descendre() -> None:
        try:
            while donnees := amont.recv(65536):
                wfile.write(donnees)
        except OSError:
            pass
        finally:
            try:
                client.shutdown(socket.SHUT_RD)
            except OSError:
                pass

    fil = threading.Thread(target=descendre, daemon=True)
    fil.start()
    try:
        while donnees := rfile.read1(65536):
            amont.sendall(donnees)
    except (OSError, ValueError):
        pass
    finally:
        try:
            amont.shutdown(socket.SHUT_WR)
        except OSError:
            pass
    fil.join(timeout=30)
    amont.close()
