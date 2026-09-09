#!/usr/bin/env python3
"""Tickets : lifecycle, transitions interdites, expiry + défaut."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import (  # noqa: E402
    TicketError,
    add_item,
    cancel,
    close,
    create_ticket,
    decide,
    discuss,
    execute,
    expire_due,
    get_ticket,
    publish,
    reopen,
    set_item,
)

NOW = '2026-09-09T19:00:00+00:00'


class TicketTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.connection.close()

    def _col(self, ticket_id: str, column: str) -> str:
        return str(
            self.connection.execute(
                f'SELECT {column} FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        )

    def test_type_inconnu_refuse(self) -> None:
        with self.assertRaises(TicketError):
            create_ticket(self.connection, self.types, 'NOPE', 'x')

    def test_expiry_issue_du_registre(self) -> None:
        hypo = create_ticket(
            self.connection, self.types, 'HYPOTHESIS', 'h', now=NOW
        )
        expected = (
            datetime.fromisoformat(NOW) + timedelta(hours=48)
        ).isoformat()
        self.assertEqual(self._col(hypo, 'expiry_at'), expected)
        self.assertEqual(
            self._col(hypo, 'default_action'), 'refus_conservateur'
        )
        fyi = create_ticket(self.connection, self.types, 'FYI', 'f', now=NOW)
        self.assertEqual(self._col(fyi, 'expiry_at'), '')

    def test_guichet_ttl_minutes_et_override(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'GUICHET', 'g', now=NOW
        )
        expected = (
            datetime.fromisoformat(NOW) + timedelta(minutes=10)
        ).isoformat()
        self.assertEqual(self._col(ticket_id, 'expiry_at'), expected)
        custom = create_ticket(
            self.connection,
            self.types,
            'GUICHET',
            'g2',
            now=NOW,
            ttl_minutes=30,
        )
        expected30 = (
            datetime.fromisoformat(NOW) + timedelta(minutes=30)
        ).isoformat()
        self.assertEqual(self._col(custom, 'expiry_at'), expected30)

    def test_lifecycle_nominal(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'VETO_AMONT', 'v', now=NOW
        )
        self.assertEqual(self._col(ticket_id, 'state'), 'DRAFT')
        publish(self.connection, ticket_id)
        discuss(self.connection, ticket_id)
        reopen(self.connection, ticket_id)
        decide(self.connection, ticket_id, 'APPROVED', note='go')
        execute(self.connection, ticket_id, {'done': True})
        close(self.connection, ticket_id)
        self.assertEqual(self._col(ticket_id, 'state'), 'CLOSED')
        kinds = [
            row[0]
            for row in self.connection.execute(
                'SELECT kind FROM ticket_events WHERE ticket_id=? ORDER BY id',
                (ticket_id,),
            )
        ]
        self.assertEqual(
            kinds,
            [
                'transition.draft',
                'transition.open',
                'transition.discussing',
                'transition.open',
                'transition.approved',
                'transition.executed',
                'transition.closed',
            ],
        )

    def test_transitions_interdites(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'POLICY', 'p', now=NOW
        )
        with self.assertRaises(TicketError):
            decide(self.connection, ticket_id, 'APPROVED')
        with self.assertRaises(TicketError):
            close(self.connection, ticket_id)
        publish(self.connection, ticket_id)
        with self.assertRaises(TicketError):
            decide(self.connection, ticket_id, 'MAYBE')
        cancel(self.connection, ticket_id, 'plus besoin')
        self.assertEqual(self._col(ticket_id, 'state'), 'CANCELLED')
        with self.assertRaises(TicketError):
            publish(self.connection, ticket_id)

    def test_edited_versionne(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'PUBLICATION', 'p', now=NOW
        )
        publish(self.connection, ticket_id)
        decide(self.connection, ticket_id, 'EDITED', note='v2')
        versions = json.loads(self._col(ticket_id, 'versions_json'))
        self.assertEqual(len(versions), 1)
        self.assertEqual(versions[0]['note'], 'v2')

    def test_expiry_applique_le_defaut(self) -> None:
        ticket_id = create_ticket(
            self.connection,
            self.types,
            'HYPOTHESIS',
            'h',
            now='2026-09-01T00:00:00+00:00',
        )
        publish(self.connection, ticket_id)
        future = create_ticket(
            self.connection, self.types, 'HYPOTHESIS', 'h2', now=NOW
        )
        publish(self.connection, future)
        expired = expire_due(self.connection, NOW)
        self.assertEqual(expired, [ticket_id])
        self.assertEqual(self._col(ticket_id, 'state'), 'EXPIRED')
        self.assertEqual(self._col(future, 'state'), 'OPEN')
        last = self.connection.execute(
            'SELECT kind, payload_json FROM ticket_events WHERE ticket_id=?'
            ' ORDER BY id DESC LIMIT 1',
            (ticket_id,),
        ).fetchone()
        self.assertEqual(last[0], 'transition.expired')
        self.assertEqual(
            json.loads(last[1])['default_applied'], 'refus_conservateur'
        )

    def test_items_memory(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'MEMORY', 'm', now=NOW
        )
        item = add_item(self.connection, ticket_id, 'lesson', 'L1')
        set_item(self.connection, item, 'keep')
        ticket = get_ticket(self.connection, ticket_id)
        self.assertEqual(len(ticket['items']), 1)
        self.assertEqual(ticket['items'][0]['state'], 'keep')
        with self.assertRaises(TicketError):
            set_item(self.connection, 'ti_nope', 'keep')
        with self.assertRaises(TicketError):
            add_item(self.connection, 't_nope', 'lesson', 'x')

    def test_get_ticket_assemble_vue(self) -> None:
        ticket_id = create_ticket(
            self.connection, self.types, 'QNA', 'q', now=NOW
        )
        publish(self.connection, ticket_id)
        add_item(self.connection, ticket_id, 'option', 'A')
        ticket = get_ticket(self.connection, ticket_id)
        self.assertEqual(ticket['id'], ticket_id)
        self.assertEqual(ticket['state'], 'OPEN')
        self.assertEqual(len(ticket['items']), 1)
        self.assertEqual(
            [event['kind'] for event in ticket['events']],
            ['transition.draft', 'transition.open'],
        )
        with self.assertRaises(TicketError):
            get_ticket(self.connection, 't_nope')


if __name__ == '__main__':
    unittest.main()
