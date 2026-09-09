#!/usr/bin/env python3
"""WebSocket minimal : frames, handshake, ping/pong (socket paire)."""

from __future__ import annotations

import socket
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.ws import (  # noqa: E402
    WsClient,
    WsError,
    accept_key,
    decode_frames,
    encode_frame,
)


class WsTests(unittest.TestCase):
    def test_accept_rfc(self) -> None:
        self.assertEqual(
            accept_key('dGhlIHNhbXBsZSBub25jZQ=='),
            's3pPLMBiTxaQ9kYGzzhZRbK+xOo=',
        )

    def test_roundtrip_frames(self) -> None:
        raw = encode_frame(b'bonjour', 0x1)
        self.assertTrue(raw[1] & 0x80)
        server = bytearray(b'\x81\x07bonjour')
        self.assertEqual(decode_frames(server), [(0x1, b'bonjour')])
        self.assertEqual(len(server), 0)
        big = bytearray(b'\x82\x7e' + (300).to_bytes(2, 'big') + b'x' * 300)
        opcode, payload = decode_frames(big)[0]
        self.assertEqual((opcode, len(payload)), (0x2, 300))
        partial = bytearray(b'\x81\x05bon')
        self.assertEqual(decode_frames(partial), [])
        self.assertEqual(len(partial), 5)

    def test_close_et_masque_rejetes(self) -> None:
        with self.assertRaises(WsError):
            decode_frames(bytearray(b'\x88\x00'))
        with self.assertRaises(WsError):
            decode_frames(bytearray(b'\x81\x85xxxxxhello'))

    def test_client_envoie_recoit(self) -> None:
        parent, child = socket.socketpair()
        child.settimeout(5)
        client = WsClient(parent, timeout=5)
        try:
            client.send_text('salut')
            data = child.recv(65536)
            self.assertEqual(data[0] & 0x0F, 0x1)
            child.sendall(b'\x81\x02ok')
            self.assertEqual(client.recv(), [(0x1, b'ok')])
        finally:
            client.close()
            child.close()

    def test_ping_pong(self) -> None:
        parent, child = socket.socketpair()
        child.settimeout(5)
        client = WsClient(parent, timeout=5)
        try:
            child.sendall(b'\x89\x04ping')
            self.assertEqual(client.recv(), [])
            pong = child.recv(65536)
            self.assertEqual(pong[0] & 0x0F, 0xA)
        finally:
            client.close()
            child.close()

    def test_connect_refuse_non_wss(self) -> None:
        with self.assertRaises(WsError):
            WsClient.connect('http://x.test/socket')


if __name__ == '__main__':
    unittest.main()
