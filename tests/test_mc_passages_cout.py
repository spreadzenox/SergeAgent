#!/usr/bin/env python3
"""MC : le coût d'un appel au modèle ne s'affiche jamais comme « gratuit »."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.proj_passages import cout  # noqa: E402


class CoutTests(unittest.TestCase):
    def test_affichage_du_cout(self) -> None:
        self.assertEqual(cout(None), '—')
        self.assertEqual(cout(0), '0,0000 $')
        self.assertEqual(cout(0.0012), '0,0012 $')
        # mistral-nemo : 0,0000096 $ pour un appel réel, pas « 0,0000 $ ».
        self.assertEqual(cout(0.0000096), '< 0,0001 $')


if __name__ == '__main__':
    unittest.main()
