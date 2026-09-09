#!/usr/bin/env python3
"""Interactions Discord : actes typés, idempotence, garde owner."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.discord.interactions import (  # noqa: E402
    actor_id,
    parse_custom_id,
    route_interaction,
)
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import add_item, create_ticket, publish  # noqa: E402

OWNER = '999988887777666555'
NOW = '2026-09-09T19:00:00+00:00'


def _interaction(
    custom_id: str,
    user_id: str = OWNER,
    interaction_id: str = '1001',
    values: list[str] | None = None,
) -> dict:
    data: dict = {'custom_id': custom_id, 'component_type': 2}
    if values is not None:
        data['values'] = values
        data['component_type'] = 3
    return {
        'id': interaction_id,
        'token': 'tok-interaction-1',
        'member': {'user': {'id': user_id}},
        'data': data,
    }


class DiscordInteractionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def _ticket(self, kind: str = 'VETO_AMONT') -> str:
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
            parse_custom_id('t:t_abc:approuver'),
            ('t_abc', 'approuver', ''),
        )
        self.assertEqual(
            parse_custom_id('t:t_abc:jeter:ti_1'), ('t_abc', 'jeter', 'ti_1')
        )
        self.assertIsNone(parse_custom_id('nope'))
        self.assertIsNone(parse_custom_id('x:t:a'))
        self.assertEqual(actor_id(_interaction('t:t:a')), OWNER)
        self.assertEqual(actor_id({}), '')

    def test_approuver_rejeter_discuter(self) -> None:
        first = self._ticket()
        result = route_interaction(
            self.conn,
            _interaction(f't:{first}:approuver', interaction_id='2001'),
            OWNER,
        )
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self._state(first), 'APPROVED')
        second = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{second}:rejeter'), OWNER
        )
        self.assertEqual(self._state(second), 'REJECTED')
        third = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{third}:discuter'), OWNER
        )
        self.assertEqual(self._state(third), 'DISCUSSING')

    def test_idempotence_double_clic(self) -> None:
        ticket_id = self._ticket()
        first = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='3001'),
            OWNER,
        )
        second = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='3001'),
            OWNER,
        )
        self.assertEqual(first['status'], 'applied')
        self.assertEqual(second['status'], 'duplicate')

    def test_non_owner_refuse_sans_ecrire(self) -> None:
        ticket_id = self._ticket()
        result = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', user_id='1111'),
            OWNER,
        )
        self.assertEqual(result['status'], 'refused')
        self.assertEqual(self._state(ticket_id), 'OPEN')

    def test_items_memory(self) -> None:
        ticket_id = self._ticket('MEMORY')
        keep = add_item(self.conn, ticket_id, 'lesson', 'L1')
        drop = add_item(self.conn, ticket_id, 'lesson', 'L2')
        route_interaction(
            self.conn,
            _interaction(
                f't:{ticket_id}:garder:{keep}', interaction_id='6001'
            ),
            OWNER,
        )
        route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:jeter:{drop}', interaction_id='6002'),
            OWNER,
        )
        states = {
            row[0]: row[1]
            for row in self.conn.execute(
                'SELECT id, state FROM ticket_items WHERE ticket_id=?',
                (ticket_id,),
            )
        }
        self.assertEqual(states, {keep: 'keep', drop: 'drop'})
        self.assertEqual(self._state(ticket_id), 'OPEN')

    def test_tout_approuver_et_qcm(self) -> None:
        memory_id = self._ticket('MEMORY')
        add_item(self.conn, memory_id, 'lesson', 'L1')
        approved = route_interaction(
            self.conn,
            _interaction(f't:{memory_id}:tout_approuver'),
            OWNER,
        )
        self.assertEqual(approved['status'], 'applied')
        self.assertEqual(self._state(memory_id), 'APPROVED')
        state = self.conn.execute(
            'SELECT state FROM ticket_items WHERE ticket_id=?', (memory_id,)
        ).fetchone()[0]
        self.assertEqual(state, 'keep')
        qna_id = self._ticket('QNA')
        route_interaction(
            self.conn,
            _interaction(
                f't:{qna_id}:choix_qcm',
                values=['Email'],
                interaction_id='4001',
            ),
            OWNER,
        )
        self.assertEqual(self._state(qna_id), 'APPROVED')

    def test_deja_decide_erreur_propre(self) -> None:
        ticket_id = self._ticket()
        route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:approuver', interaction_id='5001'),
            OWNER,
        )
        result = route_interaction(
            self.conn,
            _interaction(f't:{ticket_id}:rejeter', interaction_id='5002'),
            OWNER,
        )
        self.assertEqual(result['status'], 'error')
        self.assertEqual(self._state(ticket_id), 'APPROVED')

    def test_action_inconnue(self) -> None:
        ticket_id = self._ticket()
        result = route_interaction(
            self.conn, _interaction(f't:{ticket_id}:lancer_fusee'), OWNER
        )
        self.assertEqual(result['status'], 'error')


if __name__ == '__main__':
    unittest.main()
