#!/usr/bin/env python3
"""Page Identité : registre p9."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import PAGE_SECTIONS, SLOW_SECTIONS  # noqa: E402


class IdentitePageTests(unittest.TestCase):
    def test_registre_p9(self) -> None:
        sections = PAGE_SECTIONS['p9']
        self.assertEqual(sections[0], 'meta')
        self.assertIn('identite', sections)
        self.assertIn('identite', SLOW_SECTIONS)
