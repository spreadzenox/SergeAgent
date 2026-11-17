#!/usr/bin/env python3
"""Interactions Discord : actes typés, idempotence, administrateurs en base,
fenêtres de saisie (décision Q86)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.discord.interactions import (  # noqa: E402
    actor_id,
    parse_custom_id,
    route_interaction,
)
from serge.tickets import create_ticket, publish  # noqa: E402
from serge.tickets.admins import add_admin  # noqa: E402
from serge.tickets.types import ticket_types  # noqa: E402

OWNER = '999988887777666555'
CLEM = '111122223333444455'
NOW = '2026-09-09T19:00:00+00:00'


def _interaction(
    custom_id: str,
    user_id: str = OWNER,
    interaction_id: str = '1001',
) -> dict:
    data: dict = {'custom_id': custom_id, 'component_type': 2}
    return {
        'id': interaction_id,
        'type': 3,
        'token': 'tok-interaction-1',
        # En message privé, Discord donne ``user`` (pas ``member``).
        'user': {'id': user_id},
        'data': data,
    }


def _fenetre(
    custom_id: str,
    texte: str,
    user_id: str = OWNER,
    interaction_id: str = '9001',
) -> dict:
    return {
        'id': interaction_id,
        'type': 5,
        'token': 'tok-interaction-2',
        'user': {'id': user_id},
        'data': {
            'custom_id': custom_id,
            'components': [
                {
                    'type': 1,
                    'components': [
                        {'type': 4, 'custom_id': 'texte', 'value': texte}
                    ],
                }
            ],
        },
    }


class DiscordInteractionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        add_admin(self.conn, OWNER, 'Julien', 'test')
        add_admin(self.conn, CLEM, 'Clem', 'test')
        self.conn.commit()
        self.types = ticket_types(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def _ticket(self, kind: str = 'PLAN_POC') -> str:
        ticket_id = create_ticket(
            self.conn, self.types, kind, 'Titre', {'decision': 'x'}, now=NOW
        )
        publish(self.conn, ticket_id)
        return ticket_id

    def _state(self, ticket_id: str) -> str:
        return str(
            self.conn.execute(
                'SELECT state FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        )

    def test_parse_et_acteur(self) -> None:
        self.assertEqual(
            parse_custom_id('t:t_abc:approuver'), ('t_abc', 'approuver')
        )
        self.assertIsNone(parse_custom_id('t:t_abc:jeter:ti_1'))
        self.assertIsNone(parse_custom_id('nope'))
        self.assertIsNone(parse_custom_id('x:t:a'))
        self.assertEqual(actor_id(_interaction('t:t:a')), OWNER)
        self.assertEqual(actor_id({}), '')

    def test_approuver_rejeter_discuter(self) -> None:
        first = self._ticket()
        result = route_interaction(
            self.conn,
            _interaction(f't:{first}:approuver', interaction_id='2001'),
        )
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self._state(first), 'APPROVED')
        second = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{second}:rejeter')
        )
        self.assertEqual(self._state(second), 'REJECTED')
        # « Discuter » ouvre une fenêtre de saisie ; le message envoyé passe
        # le ticket en discussion et reste dans son fil.
        third = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{third}:discuter')
        )
        self.assertEqual(result['status'], 'modal')
        self.assertEqual(result['modal']['custom_id'], f'm:{third}:discuter')
        self.assertEqual(self._state(third), 'OPEN')
        result = route_interaction(
            self.conn, _fenetre(f'm:{third}:discuter', 'On en parle ?')
        )
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self._state(third), 'DISCUSSING')
        self.assertEqual(
            self.conn.execute(
                "SELECT actor, payload_json FROM ticket_events WHERE kind='discord.fil'"
            ).fetchone()[0],
            f'discord:{OWNER}',
        )

    def test_idempotence_double_clic(self) -> None:
        ticket_id = self._ticket()
        first = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='3001'),
        )
        second = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='3001'),
        )
        self.assertEqual(first['status'], 'applied')
        self.assertEqual(second['status'], 'duplicate')

    def test_non_owner_refuse_sans_ecrire(self) -> None:
        ticket_id = self._ticket()
        result = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', user_id='1111'),
        )
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(self._state(ticket_id), 'OPEN')

    def test_deja_decide_erreur_propre(self) -> None:
        ticket_id = self._ticket()
        route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='5001'),
        )
        result = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:rejeter', interaction_id='5002'),
        )
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self._state(ticket_id), 'APPROVED')

    def test_n_importe_quel_administrateur_tranche(self) -> None:
        ticket_id = self._ticket()
        result = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', user_id=CLEM),
        )
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(
            self.conn.execute(
                'SELECT actor FROM ticket_events WHERE ticket_id=?'
                " AND kind='transition.approved'",
                (ticket_id,),
            ).fetchone()[0],
            f'discord:{CLEM}',
        )

    def test_un_texte_s_ecrit_dans_une_fenetre(self) -> None:
        ticket_id = self._ticket()
        ouverte = route_interaction(
            self.conn, _interaction(f't:{ticket_id}:editer')
        )
        self.assertEqual(ouverte['status'], 'modal')
        champ = ouverte['modal']['components'][0]['components'][0]
        self.assertEqual((champ['type'], champ['custom_id']), (4, 'texte'))
        vide = route_interaction(
            self.conn, _fenetre(f'm:{ticket_id}:editer', '  ')
        )
        self.assertEqual(vide['status'], 'error')
        route_interaction(
            self.conn,
            _fenetre(f'm:{ticket_id}:editer', 'Baisse le prix', user_id=CLEM),
        )
        self.assertEqual(self._state(ticket_id), 'EDITED')
        note = self.conn.execute(
            'SELECT payload_json FROM ticket_events WHERE ticket_id=?'
            " AND kind='transition.edited'",
            (ticket_id,),
        ).fetchone()[0]
        self.assertIn('Baisse le prix', note)
        # « Réponse libre » ouvre aussi une fenêtre, qui tranche.
        demande = self._ticket('REQUESTED')
        libre = route_interaction(
            self.conn, _interaction(f't:{demande}:reponse_libre')
        )
        self.assertEqual(libre['status'], 'modal')
        route_interaction(
            self.conn, _fenetre(f'm:{demande}:reponse_libre', 'Par SMS')
        )
        self.assertEqual(self._state(demande), 'APPROVED')

    def test_voir_en_entier_ne_tranche_rien(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'REQUESTED',
            'Une adresse de contact',
            {
                'en_bref': 'Une adresse de contact',
                'demande': 'Le détail. ' * 400,
                'contexte': 'Le critique la demande.',
                'point_llm': 'concevoir_produit',
            },
            now=NOW,
        )
        publish(self.conn, ticket_id)
        result = route_interaction(
            self.conn, _interaction(f't:{ticket_id}:voir_en_entier')
        )
        self.assertEqual(result['status'], 'tout')
        self.assertEqual('\n'.join(result['textes']).count('détail.'), 400)
        self.assertEqual(self._state(ticket_id), 'OPEN')
        self.assertEqual(
            self.conn.execute(
                'SELECT COUNT(*) FROM ticket_answers'
            ).fetchone()[0],
            0,
        )

    def test_action_inconnue(self) -> None:
        ticket_id = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{ticket_id}:lancer_fusee')
        )
        self.assertEqual(result['status'], 'error')


if __name__ == '__main__':
    unittest.main()
