#!/usr/bin/env python3
"""Normaliseurs : natif canal → signal universel (tables)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.observe.normalize import normalize  # noqa: E402
from serge.observe.signals import Signal  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_tables_email_voix(self) -> None:
        self.assertEqual(normalize('email', 'RECEIVED'), Signal.REPLIED)
        self.assertEqual(normalize('email', 'BOUNCED'), Signal.TECH_FAIL)
        self.assertEqual(normalize('email', 'COMPLAINED'), Signal.OPT_OUT)
        self.assertEqual(normalize('email', 'OPENED'), Signal.SEEN)
        self.assertEqual(normalize('email', 'CLICKED'), Signal.ENGAGED)
        self.assertEqual(normalize('voice', 'DTMF_1'), Signal.INTENT)
        self.assertEqual(
            normalize('voice', 'NUMBER_INVALID'), Signal.TECH_FAIL
        )
        self.assertEqual(normalize('voice', 'TRANSCRIPT'), Signal.REPLIED)

    def test_inconnu_vers_other(self) -> None:
        self.assertEqual(normalize('email', 'QUELQUECHOSE'), Signal.OTHER)
        self.assertEqual(normalize('pigeon', 'ROUCOULE'), Signal.OTHER)


if __name__ == '__main__':
    unittest.main()
