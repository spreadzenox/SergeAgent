#!/usr/bin/env python3
"""Rendu Discord : carte FR, boutons registre, IDs strippés, QCM, MEMORY."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.render import (  # noqa: E402
    remaining_fr,
    render_card,
    render_digest_line,
    render_urgent_line,
)
from serge.registry import load_ticket_types  # noqa: E402

NOW = '2026-09-09T19:00:00+00:00'

GUICHET = {
    'id': 't_abc123def456',
    'type': 'GUICHET',
    'title': 'CAPTCHA compte Malt t_abc123def456',
    'state': 'OPEN',
    'payload': {
        'contexte': 'création compte',
        'progres': '90 %',
        'action_requise': 'résoudre CAPTCHA',
    },
    'expiry_at': '2026-09-09T19:12:00+00:00',
    'default_action': 'pause_propre_reproposee',
}


class DiscordRenderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.types = load_ticket_types()

    def test_compte_a_rebours(self) -> None:
        self.assertEqual(
            remaining_fr('2026-09-09T19:12:00+00:00', NOW), 'dans 12 min'
        )
        self.assertEqual(
            remaining_fr('2026-09-10T00:00:00+00:00', NOW), 'dans 5 h'
        )
        self.assertEqual(
            remaining_fr('2026-09-12T19:00:00+00:00', NOW), 'dans 3 j'
        )
        self.assertEqual(
            remaining_fr('2026-09-09T18:00:00+00:00', NOW), 'dépassée'
        )
        self.assertEqual(remaining_fr('', NOW), 'sans expiry')

    def test_carte_guichet(self) -> None:
        card = render_card(GUICHET, self.types['GUICHET'], now_iso=NOW)
        embed = card['embeds'][0]
        self.assertIn('🔴', embed['title'])
        self.assertNotIn('t_abc123def456', embed['title'])
        self.assertEqual(embed['color'], 16711680)
        self.assertIn('12 min', embed['footer']['text'])
        self.assertIn('pause_propre', embed['footer']['text'])
        buttons = card['components'][0]['components']
        labels = [button['label'] for button in buttons]
        self.assertEqual(labels, ["C'est fait", 'Abandonner', 'Discuter'])
        self.assertTrue(
            buttons[0]['custom_id'].startswith('t:t_abc123def456:cest_fait')
        )
        self.assertFalse(buttons[0]['disabled'])

    def test_etat_terminal_boutons_morts(self) -> None:
        closed = dict(GUICHET)
        closed['state'] = 'APPROVED'
        card = render_card(closed, self.types['GUICHET'], now_iso=NOW)
        buttons = card['components'][0]['components']
        self.assertTrue(all(button['disabled'] for button in buttons))

    def test_h1_prefere_au_brut(self) -> None:
        h1 = {
            'titre': 'x',
            'ou': 'Compte à 90 %.',
            'enjeu': 'Stratégique.',
            'attente': 'Résous le CAPTCHA.',
        }
        card = render_card(GUICHET, self.types['GUICHET'], h1=h1, now_iso=NOW)
        names = [field['name'] for field in card['embeds'][0]['fields']]
        self.assertIn('Où on en est', names)
        self.assertIn('Ce qu’on attend de toi', names)

    def test_qcm_select(self) -> None:
        ticket = {
            'id': 't_qcm000000001',
            'type': 'QNA',
            'title': 'Choisir le canal ?',
            'state': 'OPEN',
            'payload': {'question': '?', 'options_qcm': ['Email', 'Voix']},
            'expiry_at': '',
            'default_action': 'serge_decide_seul_logue',
        }
        card = render_card(ticket, self.types['QNA'], now_iso=NOW)
        select = card['components'][0]['components'][0]
        self.assertEqual(select['type'], 3)
        values = [item['value'] for item in select['options']]
        self.assertEqual(values, ['Email', 'Voix', '__autre__'])

    def test_memory_items(self) -> None:
        ticket = {
            'id': 't_mem000000001',
            'type': 'MEMORY',
            'title': 'Consolidation',
            'state': 'OPEN',
            'payload': {'lecons': []},
            'expiry_at': '',
            'default_action': 'auto_accepte_sauf_veto',
            'items': [
                {'id': 'ti_1', 'label': 'Relancer J+3', 'state': 'open'},
                {
                    'id': 'ti_2',
                    'label': 'Ne pas appeler lundi',
                    'state': 'open',
                },
            ],
        }
        card = render_card(ticket, self.types['MEMORY'], now_iso=NOW)
        self.assertEqual(len(card['components']), 3)
        first = card['components'][0]['components']
        self.assertTrue(first[0]['custom_id'].endswith(':ti_1'))
        last = card['components'][-1]['components']
        self.assertEqual(last[0]['label'], 'Tout approuver')

    def test_lignes_urgent_digest(self) -> None:
        line = render_urgent_line(GUICHET, '999988887777666555', NOW)
        self.assertIn('<@999988887777666555>', line)
        self.assertIn('12 min', line)
        self.assertNotIn('t_abc123def456', line)
        fyi = {
            'title': 'Résultats smoke',
            'payload': {'contenu': 'U3=3, on scale.'},
        }
        digest = render_digest_line(fyi)
        self.assertIn('Résultats smoke', digest)
        self.assertIn('U3=3', digest)


if __name__ == '__main__':
    unittest.main()
