#!/usr/bin/env python3
"""Rendu Discord : carte FR, boutons registre, IDs strippés."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.render import (  # noqa: E402
    SUITE,
    remaining_fr,
    render_card,
    texte_entier,
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
        self.assertEqual(labels, ["C'est fait", 'Abandonner'])
        self.assertTrue(
            buttons[0]['custom_id'].startswith('t:t_abc123def456:cest_fait')
        )
        self.assertFalse(buttons[0]['disabled'])

    def test_un_long_plan_montre_son_debut_et_se_lit_en_entier(self) -> None:
        """Un champ trop long pour la carte garde son début, avec « Voir en
        entier » ; le bouton poste tout le texte, en messages de 2 000
        caractères au plus, sans rien perdre (lot 11)."""
        plan = 'Le plan commence ici.\n' + 'Une étape du plan.\n' * 300
        ticket = {
            'id': 't_plan',
            'type': 'PLAN_PRODUIT',
            'title': 'Le plan d’un produit attend ton avis',
            'state': 'OPEN',
            'payload': {
                'En bref': 'nom : Calculatrice\ndomaine : calc.com\nprix : 2 €',
                'Le plan': plan,
            },
        }
        spec = self.types['PLAN_PRODUIT']
        card = render_card(ticket, spec, now_iso=NOW)
        champs = {f['name']: f['value'] for f in card['embeds'][0]['fields']}
        self.assertEqual(
            champs['En bref'],
            'nom : Calculatrice\ndomaine : calc.com\nprix : 2 €',
        )
        self.assertTrue(champs['Le plan'].startswith('Le plan commence ici.'))
        self.assertTrue(champs['Le plan'].endswith(SUITE))
        self.assertLessEqual(len(champs['Le plan']), 1024)
        boutons = [
            b['custom_id'] for r in card['components'] for b in r['components']
        ]
        self.assertIn('t:t_plan:voir_en_entier', boutons)
        messages = texte_entier(ticket, spec)
        self.assertTrue(all(len(m) <= 2000 for m in messages))
        tout = '\n'.join(messages)
        self.assertEqual(tout.count('Une étape du plan.'), 300)
        self.assertTrue(messages[0].startswith('**En bref**'))
        # Une carte qui tient en entier n'a pas ce bouton.
        court = {**ticket, 'payload': {'Le plan': 'Court.'}}
        boutons = [
            b['custom_id']
            for r in render_card(court, spec, now_iso=NOW)['components']
            for b in r['components']
        ]
        self.assertNotIn('t:t_plan:voir_en_entier', boutons)

    def test_le_fil_d_une_conversation_garde_sa_fin(self) -> None:
        fil = 'Premier message.\n' + 'Un message.\n' * 200 + 'Dernier message.'
        ticket = {
            'id': 't_conv',
            'type': 'CONVERSATION',
            'title': 'Un prospect attend',
            'state': 'OPEN',
            'payload': {'Le fil': fil},
        }
        card = render_card(ticket, self.types['CONVERSATION'], now_iso=NOW)
        champs = {f['name']: f['value'] for f in card['embeds'][0]['fields']}
        self.assertTrue(champs['Le fil'].endswith('Dernier message.'))

    def test_etat_terminal_boutons_morts(self) -> None:
        closed = dict(GUICHET)
        closed['state'] = 'APPROVED'
        card = render_card(closed, self.types['GUICHET'], now_iso=NOW)
        buttons = card['components'][0]['components']
        self.assertTrue(all(button['disabled'] for button in buttons))

    def test_un_ticket_tranche_dit_par_qui(self) -> None:
        tranche = {
            **GUICHET,
            'state': 'APPROVED',
            'tranche': 'Approuvé par Clem',
        }
        card = render_card(tranche, self.types['GUICHET'], now_iso=NOW)
        champs = {f['name']: f['value'] for f in card['embeds'][0]['fields']}
        self.assertEqual(champs['Tranché'], 'Approuvé par Clem')
        ouvert = render_card(GUICHET, self.types['GUICHET'], now_iso=NOW)
        noms = [f['name'] for f in ouvert['embeds'][0]['fields']]
        self.assertNotIn('Tranché', noms)

    def test_un_ticket_d_un_type_retire_garde_sa_carte_sans_boutons(
        self,
    ) -> None:
        """Un vieux ticket dont le type n'est plus en base : sa carte se
        lit encore, sans champ ni bouton."""
        ticket = {
            'id': 't_qna000000001',
            'type': 'QNA',
            'title': 'Choisir le canal ?',
            'state': 'OPEN',
            'payload': {'question': '?'},
            'expiry_at': '',
            'default_action': '',
        }
        card = render_card(ticket, {}, now_iso=NOW)
        self.assertIn('Choisir le canal', card['embeds'][0]['title'])
        self.assertEqual(card['embeds'][0]['fields'], [])
        self.assertEqual(card['components'], [])


if __name__ == '__main__':
    unittest.main()
