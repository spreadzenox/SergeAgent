#!/usr/bin/env python3
"""Gateway Discord : hello/identify, heartbeat, dispatch, watchdog."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.gateway import Gateway, GatewayError  # noqa: E402
from serge.voice.ws import WsError  # noqa: E402


def _frame(payload: dict) -> tuple[int, bytes]:
    return (0x1, json.dumps(payload).encode('utf-8'))


class FakeWs:
    def __init__(self, inbound: list[list[tuple[int, bytes]]]):
        self.inbound = list(inbound)
        self.sent: list[str] = []
        self.closed = False

    def send_text(self, text: str) -> None:
        self.sent.append(text)

    def recv(self) -> list[tuple[int, bytes]]:
        if not self.inbound:
            raise WsError('WS: lecture (timeout simulé)')
        return self.inbound.pop(0)

    def close(self) -> None:
        self.closed = True


HELLO = [
    [(0x1, json.dumps({'op': 10, 'd': {'heartbeat_interval': 1000}}).encode())]
]


class GatewayTests(unittest.TestCase):
    def test_connect_identify(self) -> None:
        fake = FakeWs([row for batch in HELLO for row in [batch]][:1])
        gateway = Gateway('tok-fake-30', on_event=lambda _t, _d: None)
        gateway.connect(factory=lambda _u, _h, _t: fake)
        identify = json.loads(fake.sent[0])
        self.assertEqual(identify['op'], 2)
        self.assertIn('intents', identify['d'])
        self.assertTrue(gateway.connected)
        self.assertNotIn('tok-fake-30', str(gateway.state()))

    def test_heartbeat_et_ack(self) -> None:
        fake = FakeWs(
            [
                [
                    (
                        0x1,
                        json.dumps(
                            {'op': 10, 'd': {'heartbeat_interval': 1000}}
                        ).encode(),
                    )
                ]
            ]
        )
        gateway = Gateway('tok-fake-31')
        gateway.connect(factory=lambda _u, _h, _t: fake, timeout=2.0)
        gateway.poll(now_ms=gateway.next_beat_ms)
        beat = json.loads(fake.sent[-1])
        self.assertEqual(beat['op'], 1)
        gateway.close()

    def test_dispatch_seq_ready(self) -> None:
        seen: list[str] = []
        fake = FakeWs(
            [
                [
                    (
                        0x1,
                        json.dumps(
                            {'op': 10, 'd': {'heartbeat_interval': 60000}}
                        ).encode(),
                    )
                ],
                [
                    _frame(
                        {
                            'op': 0,
                            't': 'READY',
                            's': 1,
                            'd': {'session_id': 'sess1'},
                        }
                    ),
                    _frame(
                        {
                            'op': 0,
                            't': 'MESSAGE_CREATE',
                            's': 2,
                            'd': {'content': 'hi'},
                        }
                    ),
                ],
            ]
        )
        gateway = Gateway('tok-fake-32', on_event=lambda t, _d: seen.append(t))
        gateway.connect(factory=lambda _u, _h, _t: fake, timeout=2.0)
        kinds = gateway.poll(now_ms=0)
        self.assertEqual(kinds, ['READY', 'MESSAGE_CREATE'])
        self.assertEqual(seen, ['READY', 'MESSAGE_CREATE'])
        self.assertEqual(gateway.seq, 2)
        self.assertEqual(gateway.session_id, 'sess1')

    def test_watchdog_sans_ack(self) -> None:
        fake = FakeWs(
            [
                [
                    (
                        0x1,
                        json.dumps(
                            {'op': 10, 'd': {'heartbeat_interval': 1000}}
                        ).encode(),
                    )
                ]
            ]
        )
        gateway = Gateway('tok-fake-33')
        gateway.connect(factory=lambda _u, _h, _t: fake, timeout=2.0)
        gateway.last_ack_ms = 0
        with self.assertRaisesRegex(GatewayError, '^RECONNECT'):
            gateway.poll(now_ms=5000)

    def test_reconnect_serveur_et_session_invalide(self) -> None:
        fake = FakeWs(
            [
                [
                    (
                        0x1,
                        json.dumps(
                            {'op': 10, 'd': {'heartbeat_interval': 60000}}
                        ).encode(),
                    )
                ],
                [_frame({'op': 7, 'd': None})],
            ]
        )
        gateway = Gateway('tok-fake-34')
        gateway.connect(factory=lambda _u, _h, _t: fake, timeout=2.0)
        with self.assertRaisesRegex(GatewayError, '^RECONNECT'):
            gateway.poll(now_ms=0)

    def test_token_manquant(self) -> None:
        gateway = Gateway('')
        with self.assertRaisesRegex(GatewayError, '^AUTH'):
            gateway.connect(factory=lambda _u, _h, _t: FakeWs([]))


if __name__ == '__main__':
    unittest.main()
