#!/usr/bin/env python3
"""E.164 unique : validation + normalisation."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.e164 import is_valid, normalize  # noqa: E402


class E164Tests(unittest.TestCase):
    def test_valid_numbers(self) -> None:
        for raw in ('+33612345678', '+13135550100', '+33162000001'):
            self.assertTrue(is_valid(raw), raw)

    def test_invalid_numbers(self) -> None:
        for raw in (
            '',
            'not-a-number',
            '0612345678',
            '+012345678',
            '+336123',
            '+' + '1' * 16,
        ):
            self.assertFalse(is_valid(raw), raw)

    def test_normalize_strips_separators(self) -> None:
        self.assertEqual(normalize('+336 95.17-04-42'), '+33695170442')
        self.assertTrue(is_valid('+336 95.17-04-42'))

    def test_normalize_never_adds_plus(self) -> None:
        self.assertEqual(normalize('33612345678'), '33612345678')
        self.assertFalse(is_valid('33612345678'))


if __name__ == '__main__':
    unittest.main()
