#!/usr/bin/env python3
"""Le registre des types de tickets."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.registry import (  # noqa: E402
    load_ticket_types,
    load_ticket_types_deleted,
)


class RegistryTests(unittest.TestCase):
    def test_ticket_taxonomy_complete(self) -> None:
        types = load_ticket_types()
        self.assertEqual(
            sorted(types),
            [
                'CHOIX_PRINCIPAL',
                'CONNEXION_COMPTE',
                'CONVERSATION',
                'DOMAINE_PRODUIT',
                'FYI',
                'GUICHET',
                'GUICHET_PRET',
                'LECON',
                'PASSAGE',
                'PLAN_POC',
                'PLAN_PRODUIT',
                'REQUESTED',
                'SERVICE',
                'TEST_POC',
                'TEST_PRODUIT',
            ],
        )
        self.assertEqual(
            types['GUICHET']['default'], 'pause_propre_reproposee'
        )
        self.assertEqual(types['PLAN_POC']['default'], 'valider')
        # Ni une leçon ni une adresse de connexion ne se valident seules.
        for attend in ('LECON', 'CONNEXION_COMPTE'):
            self.assertEqual(types[attend]['default'], 'attend')
            self.assertIsNone(types[attend]['expiry_hours'])

    def test_les_types_retires_sont_listes_sans_etre_declares(self) -> None:
        """La section ``deleted`` : les types retirés. Un type à la fois
        déclaré et retiré, ou une section mal écrite, est une erreur."""
        import tempfile

        from serge.policy import PolicyError

        retires = load_ticket_types_deleted()
        self.assertIn('VETO_AMONT', retires)
        self.assertEqual(set(retires) & set(load_ticket_types()), set())
        un_type = (
            'schema_version: 1\n'
            'types:\n'
            '  FYI:\n'
            '    role: Pour info\n'
            '    urgency: aucune\n'
            '    expiry_hours: null\n'
            '    default: rien\n'
            '    fields: [contenu]\n'
            '    buttons: [discuter_fil]\n'
        )
        with tempfile.TemporaryDirectory() as tmp:
            fichier = Path(tmp) / 'ticket-types.yaml'
            fichier.write_text(un_type, encoding='utf-8')
            self.assertEqual(load_ticket_types_deleted(Path(tmp)), [])
            for section in ('deleted: [FYI]\n', 'deleted: FYI\n'):
                fichier.write_text(un_type + section, encoding='utf-8')
                with self.assertRaises(PolicyError, msg=section):
                    load_ticket_types_deleted(Path(tmp))

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
