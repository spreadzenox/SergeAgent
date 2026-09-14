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


if __name__ == '__main__':
    unittest.main()
