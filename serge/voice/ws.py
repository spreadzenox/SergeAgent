#!/usr/bin/env python3
"""WebSocket client minimal (RFC 6455, stdlib) pour voix temps réel.

Frames texte/binaire, ping/pong, close, masquage client. TLS via ssl.
Testé contre socket paire (pas de réseau en unit).
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import ssl
import struct
import urllib.parse
from typing import Any

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'


class WsError(ValueError):
    pass


def encode_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """Encode une frame client (FIN + masquée).

    Args:
        payload: Octets utiles.
        opcode: 0x1 texte, 0x2 binaire, 0x8 close, 0x9 ping.

    Returns:
        La frame complète.
    """
    mask = os.urandom(4)
    masked = bytes(
        byte ^ mask[index % 4] for index, byte in enumerate(payload)
    )
    header = bytes([0x80 | opcode])
    length = len(payload)
    if length < 126:
        header += bytes([0x80 | length])
    elif length < 65536:
        header += bytes([0x80 | 126]) + struct.pack('!H', length)
    else:
        header += bytes([0x80 | 127]) + struct.pack('!Q', length)
    return header + mask + masked


def decode_frames(buffer: bytearray) -> list[tuple[int, bytes]]:
    """Décode les frames serveur complètes (non masquées).

    Args:
        buffer: Tampon (frames consommées retirées).

    Returns:
        Liste (opcode, payload). Incomplètes gardées en tampon.

    Raises:
        WsError: Frame masquée serveur ou close reçue.
    """
    out: list[tuple[int, bytes]] = []
    while len(buffer) >= 2:
        first, second = buffer[0], buffer[1]
        opcode = first & 0x0F
        if second & 0x80:
            raise WsError('WS: frame serveur masquée')
        length = second & 0x7F
        offset = 2
        if length == 126:
            if len(buffer) < 4:
                break
            (length,) = struct.unpack('!H', bytes(buffer[2:4]))
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                break
            (length,) = struct.unpack('!Q', bytes(buffer[2:10]))
            offset = 10
        if len(buffer) < offset + length:
            break
        out.append((opcode, bytes(buffer[offset : offset + length])))
        del buffer[: offset + length]
        if opcode == 0x8:
            raise WsError('WS: close serveur')
    return out


def accept_key(client_key: str) -> str:
    """Clé Sec-WebSocket-Accept (RFC 6455).

    Args:
        client_key: Clé du client (base64).

    Returns:
        L'accept attendue.
    """
    digest = hashlib.sha1((client_key + GUID).encode()).digest()
    return base64.b64encode(digest).decode()


class WsClient:
    """Client WS sur socket fournie (connect() pour wss:// réel)."""

    def __init__(self, sock: Any, timeout: float = 20.0):
        self.sock = sock
        self.sock.settimeout(timeout)
        self.buffer = bytearray()

    @classmethod
    def connect(
        cls,
        url: str,
        headers: dict[str, str] | None = None,
        timeout: float = 20.0,
    ) -> WsClient:
        """Connecte wss:// (handshake + vérif accept).

        Args:
            url: URL wss:// (path + query inclus).
            headers: Headers extra (Authorization...).
            timeout: Timeout socket.

        Returns:
            Client connecté.

        Raises:
            WsError: Schéma, handshake, réseau.
        """
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != 'wss' or not parsed.hostname:
            raise WsError('WS: URL wss:// requise')
        port = parsed.port or 443
        try:
            raw = socket.create_connection(
                (parsed.hostname, port), timeout=timeout
            )
            context = ssl.create_default_context()
            sock: Any = context.wrap_socket(
                raw, server_hostname=parsed.hostname
            )
        except OSError as exc:
            raise WsError(f'WS: connexion ({exc})') from exc
        key = base64.b64encode(os.urandom(16)).decode()
        path = parsed.path or '/'
        if parsed.query:
            path += f'?{parsed.query}'
        lines = [
            f'GET {path} HTTP/1.1',
            f'Host: {parsed.hostname}:{port}',
            'Upgrade: websocket',
            'Connection: Upgrade',
            f'Sec-WebSocket-Key: {key}',
            'Sec-WebSocket-Version: 13',
        ]
        for name, value in (headers or {}).items():
            lines.append(f'{name}: {value}')
        try:
            sock.sendall(('\r\n'.join(lines) + '\r\n\r\n').encode())
            head = b''
            while b'\r\n\r\n' not in head:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                head += chunk
        except OSError as exc:
            raise WsError(f'WS: handshake ({exc})') from exc
        text = head.decode('latin-1')
        if ' 101 ' not in text.split('\r\n', 1)[0]:
            raise WsError('WS: handshake refusé (pas 101)')
        accepted = ''
        for line in text.split('\r\n'):
            if line.lower().startswith('sec-websocket-accept:'):
                accepted = line.split(':', 1)[1].strip()
        if accepted != accept_key(key):
            raise WsError('WS: accept invalide')
        return cls(sock, timeout)

    def send_text(self, text: str) -> None:
        """Envoie une frame texte.

        Raises:
            WsError: Socket rompue.
        """
        try:
            self.sock.sendall(encode_frame(text.encode('utf-8'), 0x1))
        except OSError as exc:
            raise WsError(f'WS: envoi ({exc})') from exc

    def send_binary(self, payload: bytes) -> None:
        """Envoie une frame binaire (audio).

        Raises:
            WsError: Socket rompue.
        """
        try:
            self.sock.sendall(encode_frame(payload, 0x2))
        except OSError as exc:
            raise WsError(f'WS: envoi ({exc})') from exc

    def recv(self) -> list[tuple[int, bytes]]:
        """Lit les frames disponibles (ping → pong auto).

        Returns:
            Frames (opcode, payload), sans les ping.

        Raises:
            WsError: Timeout, close, socket.
        """
        try:
            chunk = self.sock.recv(65536)
        except (TimeoutError, OSError) as exc:
            raise WsError(f'WS: lecture ({exc})') from exc
        if not chunk:
            raise WsError('WS: connexion fermée')
        self.buffer += chunk
        frames = decode_frames(self.buffer)
        out: list[tuple[int, bytes]] = []
        for opcode, payload in frames:
            if opcode == 0x9:
                try:
                    self.sock.sendall(encode_frame(payload, 0xA))
                except OSError as exc:
                    raise WsError(f'WS: pong ({exc})') from exc
                continue
            out.append((opcode, payload))
        return out

    def close(self) -> None:
        """Ferme poliment (best effort)."""
        try:
            self.sock.sendall(encode_frame(b'', 0x8))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass
