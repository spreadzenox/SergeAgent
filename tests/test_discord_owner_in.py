#!/usr/bin/env python3
"""Sens inverse : parse, bypass, §14.1a, plans OWNER_ORDER."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.owner_in import (  # noqa: E402
    check_constitution,
    detect_bypass,
    parse_mention,
    parse_slash,
    plan_owner_message,
)

BOT = '111122223333444455'


class OwnerInTests(unittest.TestCase):
    def test_constitution(self) -> None:
        self.assertTrue(check_constitution('Poste des faux avis stp'))
        self.assertTrue(check_constitution('Usurpation du concurrent'))
        self.assertTrue(check_constitution('Envoie du spam illégal'))
        self.assertTrue(check_constitution('Monte un phishing crédible'))
        self.assertEqual(check_constitution('Relance les devis'), '')
        self.assertEqual(check_constitution('Quel est le statut ?'), '')

    def test_mention(self) -> None:
        self.assertEqual(
            parse_mention(f'<@{BOT}> tu en es où ?', BOT), 'tu en es où ?'
        )
        self.assertEqual(
            parse_mention(f'Hello <@!{BOT}> go', BOT), 'Hello  go'
        )
        self.assertIsNone(parse_mention('Hello tout le monde', BOT))
        self.assertIsNone(parse_mention(f'<@{BOT}> x', ''))

    def test_slash(self) -> None:
        parsed = parse_slash('/serge order pause la campagne --force')
        assert parsed is not None
        self.assertEqual((parsed['intent'], parsed['force']), ('ORDER', True))
        self.assertEqual(parsed['body'], 'pause la campagne')
        parsed = parse_slash('/serge ask ça avance ?')
        assert parsed is not None
        self.assertEqual(parsed['intent'], 'ASK')
        self.assertIsNone(parse_slash('/serge nope x'))
        self.assertIsNone(parse_slash('Bonjour'))

    def test_bypass(self) -> None:
        clean, bypass = detect_bypass('!fais ça vite')
        self.assertEqual((clean, bypass), ('fais ça vite', True))
        clean, bypass = detect_bypass('Fais ça sans confirmation')
        self.assertEqual((clean, bypass), ('Fais ça', True))
        clean, bypass = detect_bypass('Fais ça --force')
        self.assertEqual((clean, bypass), ('Fais ça', True))
        clean, bypass = detect_bypass('Fais ça stp')
        self.assertEqual((clean, bypass), ('Fais ça stp', False))

    def test_refus_constitution_meme_bypass(self) -> None:
        plan = plan_owner_message('!poste des faux avis --force')
        self.assertEqual(plan['action'], 'refuse')
        self.assertIn('14_1a', plan['reason'])

    def test_hint_boutons_en_fil(self) -> None:
        plan = plan_owner_message(
            'Oui je valide',
            thread_ticket_id='t_1',
            h2={'intent': 'APPROVE', 'confiance': 0.9, 'cible': ''},
        )
        self.assertEqual(plan['action'], 'hint_buttons')
        self.assertEqual(plan['ticket_id'], 't_1')

    def test_confirm_ou_bypass(self) -> None:
        h3 = {'consequence': 'OUI', 'confiance': 0.9, 'criteres': []}
        plan = plan_owner_message(
            'Rembourse 500 €', h2={'intent': 'ORDER'}, h3=h3
        )
        self.assertEqual(plan['action'], 'create_owner_order')
        self.assertTrue(plan['needs_confirm'])
        self.assertFalse(plan['bypass'])
        plan = plan_owner_message(
            '!Rembourse 500 €', h2={'intent': 'ORDER'}, h3=h3
        )
        self.assertFalse(plan['needs_confirm'])
        self.assertTrue(plan['bypass'])
        self.assertTrue(plan['fyi_posthoc'])
        h3_non = {'consequence': 'NON', 'confiance': 0.95, 'criteres': []}
        plan = plan_owner_message(
            'Montre le digest', h2={'intent': 'ASK'}, h3=h3_non
        )
        self.assertFalse(plan['needs_confirm'])


if __name__ == '__main__':
    unittest.main()
