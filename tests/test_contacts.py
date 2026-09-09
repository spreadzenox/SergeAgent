#!/usr/bin/env python3
"""Contacts : états nommés, branches terminales, régimes."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.funnels.contacts import (  # noqa: E402
    ContactError,
    create_contact,
    mark_blocked,
    mark_engaged,
    mark_intent,
    mark_invalid,
    mark_unreachable,
    note_inbound,
    opt_out,
    qualify,
    refresh_regime,
    reject,
    start_contacting,
    to_customer,
    to_meeting,
)

NOW = '2026-09-09T19:00:00+00:00'


class ContactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def _make(self) -> str:
        return create_contact(self.connection, 'v1', 'Ada', email='ada@x.io')

    def _state(self, contact_id: str) -> tuple[str, str]:
        row = self.connection.execute(
            'SELECT funnel_state, regime FROM contacts WHERE id=?',
            (contact_id,),
        ).fetchone()
        return str(row[0]), str(row[1])

    def test_chemin_nominal_jusqu_client(self) -> None:
        contact_id = self._make()
        self.assertEqual(self._state(contact_id), ('NEW', 'OUTBOUND'))
        qualify(self.connection, contact_id)
        start_contacting(self.connection, contact_id)
        mark_engaged(self.connection, contact_id)
        mark_intent(self.connection, contact_id)
        to_meeting(self.connection, contact_id)
        to_customer(self.connection, contact_id)
        self.assertEqual(self._state(contact_id)[0], 'CUSTOMER')

    def test_transitions_interdites(self) -> None:
        contact_id = self._make()
        with self.assertRaises(ContactError):
            start_contacting(self.connection, contact_id)
        with self.assertRaises(ContactError):
            mark_intent(self.connection, contact_id)
        reject(self.connection, contact_id, 'non-ICP')
        with self.assertRaises(ContactError):
            qualify(self.connection, contact_id)

    def test_branches_definitives(self) -> None:
        unreachable = self._make()
        qualify(self.connection, unreachable)
        start_contacting(self.connection, unreachable)
        mark_unreachable(self.connection, unreachable)
        self.assertEqual(self._state(unreachable)[0], 'UNREACHABLE')
        opted = self._make()
        opt_out(self.connection, opted)
        self.assertEqual(self._state(opted)[0], 'OPTED_OUT')
        blocked = self._make()
        mark_blocked(self.connection, blocked, 'plainte')
        self.assertEqual(self._state(blocked)[0], 'BLOCKED')
        invalid = self._make()
        mark_invalid(self.connection, invalid, 'bounce 550')
        self.assertEqual(self._state(invalid)[0], 'INVALID')
        with self.assertRaises(ContactError):
            opt_out(self.connection, invalid)

    def test_regimes_inbound_silence(self) -> None:
        contact_id = self._make()
        self.assertEqual(
            note_inbound(
                self.connection, contact_id, '2026-09-01T00:00:00+00:00'
            ),
            'INBOUND',
        )
        self.assertEqual(self._state(contact_id)[1], 'INBOUND')
        regime = refresh_regime(
            self.connection, contact_id, 7, '2026-09-05T00:00:00+00:00'
        )
        self.assertEqual(regime, 'INBOUND')
        regime = refresh_regime(
            self.connection, contact_id, 7, '2026-09-10T00:00:00+00:00'
        )
        self.assertEqual(regime, 'OUTBOUND')
        kinds = [
            row[0]
            for row in self.connection.execute(
                'SELECT type FROM events ORDER BY id'
            )
        ]
        self.assertEqual(kinds, ['contact.inbound', 'contact.outbound'])


if __name__ == '__main__':
    unittest.main()
