#!/usr/bin/env python3
"""Temps réel : session, routeur événements, erreurs → degrade."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.realtime import (  # noqa: E402
    RealtimeCall,
    RealtimeError,
    build_audio_append,
    build_response_create,
    build_session_update,
    build_text_item,
    route_event,
)


class FakeSocket:
    def __init__(self, inbound: list[bytes]):
        self.inbound = list(inbound)
        self.sent: list[bytes] = []
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        pass

    def sendall(self, data: bytes) -> None:
        self.sent.append(bytes(data))

    def recv(self, size: int) -> bytes:
        if not self.inbound:
            raise TimeoutError('vide')
        return self.inbound.pop(0)

    def close(self) -> None:
        self.closed = True


def _server_frame(payload: dict) -> bytes:
    raw = json.dumps(payload).encode()
    return b'\x81' + bytes([len(raw)]) + raw


class RealtimeTests(unittest.TestCase):
    def test_session_update_shape(self) -> None:
        event = build_session_update('instructions', voice='alloy')
        session = event['session']
        self.assertEqual(session['voice'], 'alloy')
        self.assertIn('audio', session['modalities'])
        self.assertEqual(session['input_audio_format'], 'pcm16')
        self.assertEqual(
            build_audio_append('xx')['type'], 'input_audio_buffer.append'
        )
        self.assertEqual(build_response_create()['type'], 'response.create')
        item = build_text_item('revenons à notre sujet')
        self.assertEqual(item['item']['role'], 'user')

    def test_routeur(self) -> None:
        state: dict = {}
        self.assertEqual(
            route_event(
                {'type': 'response.audio.delta', 'delta': 'QQ=='}, state
            ),
            [('audio', 'QQ==')],
        )
        self.assertEqual(state['audio'], ['QQ=='])
        actions = route_event(
            {
                'type': 'response.audio_transcript.done',
                'transcript': 'Bonjour.',
            },
            state,
        )
        self.assertEqual(actions, [('transcript', 'Bonjour.')])
        self.assertEqual(
            route_event({'type': 'response.done', 'response': {}}, state),
            [('done', {})],
        )
        self.assertTrue(state['done'])
        self.assertEqual(route_event({'type': 'ping.inconnu'}, state), [])
        error = route_event({'type': 'error', 'error': {'code': 'x'}}, state)
        self.assertEqual(error[0][0], 'error')

    def test_session_envoie_update(self) -> None:
        sock = FakeSocket([])
        from serge.voice.ws import WsClient

        call = RealtimeCall(WsClient(sock), 'instructions test')
        raw = b''.join(sock.sent)
        length = raw[1] & 0x7F
        if length == 126:
            mask, payload = raw[4:8], raw[8:]
        else:
            mask, payload = raw[2:6], raw[6:]
        sent = bytes(
            byte ^ mask[index % 4] for index, byte in enumerate(payload)
        ).decode()
        self.assertIn('session.update', sent)
        self.assertIn('instructions test', sent)
        call.close()
        self.assertTrue(sock.closed)

    def test_poll_transcript_et_audio(self) -> None:
        sock = FakeSocket(
            [
                _server_frame(
                    {'type': 'response.audio.delta', 'delta': 'QQ=='}
                ),
                _server_frame(
                    {
                        'type': 'response.audio_transcript.done',
                        'transcript': 'Salut.',
                    }
                ),
            ]
        )
        from serge.voice.ws import WsClient

        call = RealtimeCall(WsClient(sock), 'i')
        self.assertEqual(call.poll(), [('audio', 'QQ==')])
        self.assertEqual(call.poll(), [('transcript', 'Salut.')])
        self.assertEqual(call.state['transcript'], 'Salut.')

    def test_erreur_provider_leve(self) -> None:
        sock = FakeSocket(
            [_server_frame({'type': 'error', 'error': {'code': 'boom'}})]
        )
        from serge.voice.ws import WsClient

        call = RealtimeCall(WsClient(sock), 'i')
        with self.assertRaisesRegex(RealtimeError, '^PROVIDER'):
            call.poll()

    def test_dial_valide(self) -> None:
        with self.assertRaisesRegex(RealtimeError, '^PROVIDER'):
            RealtimeCall.dial('nope', 'k', 'm', 'i')
        with self.assertRaisesRegex(RealtimeError, '^PROVIDER'):
            RealtimeCall.dial('openai', '', 'm', 'i')


if __name__ == '__main__':
    unittest.main()
