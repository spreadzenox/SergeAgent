#!/usr/bin/env python3
"""Registres versionnés: points LLM (matrice C) et types de tickets (H)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.registry import (  # noqa: E402
    llm_enabled,
    load_llm_points,
    load_ticket_types,
)


class RegistryTests(unittest.TestCase):
    def test_llm_registry_complete(self) -> None:
        points = load_llm_points()
        # Matrice C : 29 points + guide installateur.
        self.assertGreaterEqual(len(points), 29)
        for name in (
            'qualify_prospect',
            'voice_dialog',
            'build_artifact',
            'review_build',
            'classify_reply',
            'draft_price',
            'judge_allocator',
            'consolidate',
            'judge_consequence',
            'cluster_demand',
            'install_guide',
        ):
            self.assertIn(name, points)
            self.assertTrue(points[name]['enabled'])
        self.assertEqual(points['build_artifact']['tier'], 'T3')
        self.assertEqual(points['judge_allocator']['tier'], 'T3')
        self.assertEqual(points['qualify_prospect']['tier'], 'T1')

    def test_kill_switch_defaults_closed_on_unknown(self) -> None:
        self.assertTrue(llm_enabled('qualify_prospect'))
        self.assertFalse(llm_enabled('nope_unknown_point'))

    def test_ticket_taxonomy_complete(self) -> None:
        types = load_ticket_types()
        for name in (
            'HYPOTHESIS',
            'VETO_AMONT',
            'GUICHET',
            'PUBLICATION',
            'MEMORY',
            'POLICY',
            'R1_OVERRIDE',
            'FYI',
            'REQUESTED',
            'OWNER_ORDER',
            'QNA',
            'ALERT',
            'COLLECT_READINESS',
        ):
            self.assertIn(name, types)
        self.assertEqual(
            types['GUICHET']['default'], 'pause_propre_reproposee'
        )
        self.assertTrue(types['GUICHET']['mirror_urgent'])
        self.assertEqual(types['MEMORY']['default'], 'auto_accepte_sauf_veto')

    def test_ticket_render_blocks(self) -> None:
        types = load_ticket_types()
        for name, spec in types.items():
            render = spec.get('render')
            self.assertIsNotNone(render, name)
            assert isinstance(render, dict)
            self.assertIsInstance(render['color'], int)
            self.assertGreaterEqual(render['color'], 0)
            self.assertLessEqual(render['color'], 0xFFFFFF)
            self.assertTrue(render['emoji'], name)
        self.assertEqual(types['GUICHET']['render']['emoji'], '🔴')


if __name__ == '__main__':
    unittest.main()
