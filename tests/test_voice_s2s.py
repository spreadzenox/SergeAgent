#!/usr/bin/env python3
"""S2S : xAI puis OpenAI, refus sans clé, pas de réseau."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.audiosocket import encode  # noqa: E402
from serge.voice.realtime import RealtimeError  # noqa: E402
from serge.voice.s2s import OPENING, open_session, pump  # noqa: E402


class S2sTests(unittest.TestCase):
    def test_refuse_sans_cle(self) -> None:
        with self.assertRaisesRegex(RealtimeError, r'^PROVIDER'):
            open_session({'openai': '', 'xai': ''})

    def test_xai_avant_openai(self) -> None:
        seen: list[str] = []

        def fake_dial(provider: str, *args: object, **kwargs: object):
            seen.append(provider)
            fake = mock.Mock()
            fake.provider = provider
            return fake

        with mock.patch(
            'serge.voice.s2s.RealtimeCall.dial',
            side_effect=fake_dial,
        ):
            session = open_session({'xai': 'xk', 'openai': 'ok'})
        self.assertEqual(seen, ['xai'])
        self.assertEqual(session.provider, 'xai')

    def test_openai_si_xai_echoue(self) -> None:
        seen: list[str] = []

        def fake_dial(provider: str, *args: object, **kwargs: object):
            seen.append(provider)
            if provider == 'xai':
                raise RealtimeError('WS: xai')
            fake = mock.Mock()
            fake.provider = provider
            return fake

        with mock.patch(
            'serge.voice.s2s.RealtimeCall.dial',
            side_effect=fake_dial,
        ):
            session = open_session({'xai': 'xk', 'openai': 'ok'})
        self.assertEqual(seen, ['xai', 'openai'])
        self.assertEqual(session.provider, 'openai')

    def test_pump_refuse_sans_cle(self) -> None:
        import socket

        left, right = socket.socketpair()
        try:
            with mock.patch(
                'serge.voice.s2s.secrets',
                return_value={'openai': '', 'xai': ''},
            ):
                with self.assertRaisesRegex(RealtimeError, r'^PROVIDER'):
                    pump(left, max_s=0.2)
        finally:
            left.close()
            right.close()

    def test_pump_hangup_ferme_la_session(self) -> None:
        import socket

        fake = mock.Mock()
        fake.ws.sock = mock.Mock()
        fake.poll.return_value = []
        left, right = socket.socketpair()
        try:
            right.sendall(encode('uuid', b'x' * 16) + encode('hangup'))
            with mock.patch('serge.voice.s2s.open_session', return_value=fake):
                pump(left, max_s=1)
            frame = right.recv(4096)
        finally:
            right.close()
        fake.inject_text.assert_called_once_with(OPENING)
        fake.close.assert_called()
        self.assertEqual(frame[:1], bytes([0x10]))


if __name__ == '__main__':
    unittest.main()
