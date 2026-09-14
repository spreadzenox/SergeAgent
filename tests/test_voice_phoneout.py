#!/usr/bin/env python3
"""File 20 ms : une frame pile, trop court refusé."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.voice.phoneout import FRAME_8K, take_frame  # noqa: E402


class PhoneOutTests(unittest.TestCase):
    def test_frame_20ms_puis_refuse(self) -> None:
        buf = bytearray(b'\x01' * (FRAME_8K + 10))
        frame = take_frame(buf)
        self.assertIsNotNone(frame)
        self.assertEqual(len(frame or b''), FRAME_8K)
        self.assertEqual(len(buf), 10)
        self.assertIsNone(take_frame(buf))


if __name__ == '__main__':
    unittest.main()
