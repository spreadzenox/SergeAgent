#!/usr/bin/env python3
"""Le registre des types de tickets."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.registry import load_ticket_types  # noqa: E402


class RegistryTests(unittest.TestCase):
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
