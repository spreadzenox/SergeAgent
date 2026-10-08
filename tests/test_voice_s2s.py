#!/usr/bin/env python3
"""S2S : les fournisseurs dans l'ordre réglé en base, refus sans clé.

La pompe AudioSocket complète est dans ``tests/test_canal_appel.py``.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.realtime import RealtimeError  # noqa: E402
from serge.voice.s2s import open_session  # noqa: E402

# Les réglages de l'agent vocal en base (pipeline.yaml).
REGLAGES = {
    'fournisseurs': 'xai,openai',
    'modele_xai': 'grok-voice',
    'modele_openai': 'gpt-realtime',
}


class S2sTests(unittest.TestCase):
    def test_refuse_sans_cle(self) -> None:
        with self.assertRaisesRegex(RealtimeError, r'^PROVIDER'):
            open_session({'openai': '', 'xai': ''}, cfg=REGLAGES)

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
            session = open_session({'xai': 'xk', 'openai': 'ok'}, cfg=REGLAGES)
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
            session = open_session({'xai': 'xk', 'openai': 'ok'}, cfg=REGLAGES)
        self.assertEqual(seen, ['xai', 'openai'])
        self.assertEqual(session.provider, 'openai')


if __name__ == '__main__':
    unittest.main()
