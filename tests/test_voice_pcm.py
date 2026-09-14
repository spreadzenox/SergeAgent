#!/usr/bin/env python3
"""Rééchantillonnage 8 kHz ↔ 24 kHz : longueurs et silence."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.pcm import (  # noqa: E402
    downsample_24k_to_8k,
    is_speech,
    to_model_rate,
    to_phone_rate,
    upsample_8k_to_24k,
)


class PcmTests(unittest.TestCase):
    def test_deux_samples_deviennent_six(self) -> None:
        slin = b'\x00\x10\x00\x20'
        up = upsample_8k_to_24k(slin)
        self.assertEqual(len(up), 12)
        back = downsample_24k_to_8k(up)
        self.assertEqual(len(back), 4)

    def test_vide_et_reste_court(self) -> None:
        self.assertEqual(upsample_8k_to_24k(b''), b'')
        self.assertEqual(downsample_24k_to_8k(b'\x00\x01'), b'')

    def test_silence_refuse_parole_passe(self) -> None:
        self.assertFalse(is_speech(b'\x00\x00' * 80))
        loud = (10000).to_bytes(2, 'little', signed=True) * 80
        self.assertTrue(is_speech(loud))

    def test_8k_passe_droit(self) -> None:
        slin = b'\x01\x00\x02\x00'
        self.assertEqual(to_model_rate(slin, 8000), slin)
        out, rest = to_phone_rate(slin, b'', 8000)
        self.assertEqual(out, slin)
        self.assertEqual(rest, b'')


if __name__ == '__main__':
    unittest.main()
