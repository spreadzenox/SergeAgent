#!/usr/bin/env python3
"""AudioSocket TLV : aller-retour + refus de type inconnu."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.audiosocket import (  # noqa: E402
    AudioSocketError,
    decode_one,
    encode,
)


class AudioSocketTests(unittest.TestCase):
    def test_aller_retour_audio(self) -> None:
        frame = encode('audio', b'\x01\x02')
        buf = bytearray(frame + encode('hangup'))
        self.assertEqual(decode_one(buf), ('audio', b'\x01\x02'))
        self.assertEqual(decode_one(buf), ('hangup', b''))
        self.assertIsNone(decode_one(buf))

    def test_incomplet_attend(self) -> None:
        frame = encode('uuid', b'abcdefghijklmnop')
        self.assertIsNone(decode_one(bytearray(frame[:4])))

    def test_refuse_type_inconnu(self) -> None:
        with self.assertRaisesRegex(AudioSocketError, r'^PROTO'):
            decode_one(bytearray(b'\xff\x00\x00'))
        with self.assertRaisesRegex(AudioSocketError, r'^PROTO'):
            encode('audio', b'x' * 65536)


if __name__ == '__main__':
    unittest.main()
