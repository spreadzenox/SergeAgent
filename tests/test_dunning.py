#!/usr/bin/env python3
"""Relances : J+7, J+14, STOP + ticket après 2."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect import create_intent, to_issued, to_sent  # noqa: E402
from serge.collect.dunning import due_reminders, record_reminder  # noqa: E402
from serge.db.schema import init_schema  # noqa: E402

POLICY = {'collect': {'dunning_days': [7, 14]}}
T0 = '2026-09-01T00:00:00+00:00'


class DunningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        self.connection.row_factory = sqlite3.Row
        init_schema(self.connection)
        self.connection.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.connection.commit()
        self.tx_id = create_intent(self.connection, 'v1', 'invoice', 29.0)
        to_issued(self.connection, self.tx_id, 'F-1')
        to_sent(self.connection, self.tx_id)
        self.connection.execute(
            "UPDATE transactions SET status='overdue', updated_at=?"
            ' WHERE id=?',
            (T0, self.tx_id),
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_rien_avant_j7(self) -> None:
        due = due_reminders(
            self.connection, 'v1', POLICY, '2026-09-05T00:00:00+00:00'
        )
        self.assertEqual(due, [])

    def test_j7_polie_puis_j14_ferme_puis_stop(self) -> None:
        day8 = '2026-09-09T00:00:00+00:00'
        due = due_reminders(self.connection, 'v1', POLICY, day8)
        self.assertEqual(
            due, [{'tx_id': self.tx_id, 'level': 0, 'action': 'remind'}]
        )
        record_reminder(self.connection, self.tx_id, 0, day8)
        due = due_reminders(self.connection, 'v1', POLICY, day8)
        self.assertEqual(due, [])
        day16 = '2026-09-17T00:00:00+00:00'
        due = due_reminders(self.connection, 'v1', POLICY, day16)
        self.assertEqual(
            due, [{'tx_id': self.tx_id, 'level': 1, 'action': 'remind'}]
        )
        record_reminder(self.connection, self.tx_id, 1, day16)
        day20 = '2026-09-21T00:00:00+00:00'
        due = due_reminders(self.connection, 'v1', POLICY, day20)
        self.assertEqual(
            due, [{'tx_id': self.tx_id, 'level': 2, 'action': 'ticket_stop'}]
        )
        kinds = [
            row[0]
            for row in self.connection.execute(
                "SELECT type FROM events WHERE type='collect.reminder'"
            )
        ]
        self.assertEqual(len(kinds), 2)

    def test_inconnue_leve(self) -> None:
        with self.assertRaises(ValueError):
            record_reminder(self.connection, 'tx_nope', 0)


if __name__ == '__main__':
    unittest.main()
