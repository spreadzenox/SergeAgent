#!/usr/bin/env python3
"""Couche A : clamps allocation (plafonds + réserve), logués."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.allocator.guards import clamp_allocations  # noqa: E402

POLICY = {
    'budget': {
        'allocator_reserve_ratio': 0.20,
        'allocator_max_unproven_ratio': 0.30,
        'allocator_max_single_channel_ratio': 0.60,
    }
}


class AllocatorGuardsTests(unittest.TestCase):
    def test_reserve_et_somme(self) -> None:
        result = clamp_allocations(
            POLICY, {'c1': 0.5, 'c2': 0.5}, {'c1', 'c2'}
        )
        self.assertAlmostEqual(
            sum(result['allocations'].values()), 0.8, places=3
        )
        self.assertEqual(result['reserve'], 0.20)
        self.assertEqual(result['log'], [])

    def test_plafond_canal(self) -> None:
        result = clamp_allocations(
            POLICY, {'c1': 0.9, 'c2': 0.1}, {'c1', 'c2'}
        )
        self.assertLessEqual(result['allocations']['c1'], 0.60 * 0.8 + 0.001)
        self.assertTrue(any('clamp' in entry for entry in result['log']))

    def test_plafond_non_prouve(self) -> None:
        result = clamp_allocations(POLICY, {'c1': 0.8, 'c2': 0.2}, {'c2'})
        self.assertLessEqual(result['allocations']['c1'], 0.30 + 0.001)
        self.assertTrue(any('non-prouvé' in entry for entry in result['log']))

    def test_vide_et_nul(self) -> None:
        result = clamp_allocations(POLICY, {}, set())
        self.assertEqual(result['allocations'], {})
        result = clamp_allocations(POLICY, {'c1': 0.0, 'c2': 0.0}, set())
        self.assertAlmostEqual(
            sum(result['allocations'].values()), 0.8, places=3
        )


if __name__ == '__main__':
    unittest.main()
