#!/usr/bin/env python3
"""Collect : intents, devis, émission, paid, refunds, canary."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect import (  # noqa: E402
    CollectError,
    cancel,
    create_canary,
    create_intent,
    mark_overdue,
    mark_paid,
    request_refund,
    to_issued,
    to_quote_draft,
    to_quote_sent,
    to_quote_signed,
    to_sent,
)
from serge.db.schema import init_schema  # noqa: E402

POLICY = {'collect': {'refund_auto_max_eur': 5.0}}


class CollectTests(unittest.TestCase):
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

    def _status(self, intent_id: str) -> str:
        return str(
            self.connection.execute(
                'SELECT status FROM transactions WHERE id=?', (intent_id,)
            ).fetchone()[0]
        )

    def test_prix_requis_jamais_invente(self) -> None:
        with self.assertRaises(CollectError):
            create_intent(self.connection, 'v1', 'invoice', 0)
        with self.assertRaises(CollectError):
            create_intent(self.connection, 'v1', 'nope', 10.0)

    def test_cycle_direct_facture(self) -> None:
        intent_id = create_intent(self.connection, 'v1', 'invoice', 29.0)
        self.assertEqual(self._status(intent_id), 'draft')
        with self.assertRaises(CollectError):
            to_issued(self.connection, intent_id, ' ')
        to_issued(self.connection, intent_id, 'F-2026-0001')
        to_sent(self.connection, intent_id)
        mark_paid(self.connection, intent_id, {'rail': 'stripe'})
        self.assertEqual(self._status(intent_id), 'paid')
        envelope = json.loads(
            self.connection.execute(
                'SELECT receipt_json FROM transactions WHERE id=?',
                (intent_id,),
            ).fetchone()[0]
        )
        self.assertEqual(envelope['receipt'], {'rail': 'stripe'})

    def test_cycle_devis_b2b(self) -> None:
        intent_id = create_intent(
            self.connection, 'v1', 'invoice', 990.0, requires_quote=True
        )
        with self.assertRaises(CollectError):
            to_issued(self.connection, intent_id, 'F-1')
        to_quote_draft(self.connection, intent_id)
        to_quote_sent(self.connection, intent_id)
        to_quote_signed(self.connection, intent_id)
        to_issued(self.connection, intent_id, 'F-2026-0002')
        self.assertEqual(self._status(intent_id), 'issued')

    def test_overdue_cancel(self) -> None:
        intent_id = create_intent(self.connection, 'v1', 'invoice', 29.0)
        to_issued(self.connection, intent_id, 'F-1')
        to_sent(self.connection, intent_id)
        mark_overdue(self.connection, intent_id)
        self.assertEqual(self._status(intent_id), 'overdue')
        cancel(self.connection, intent_id)
        self.assertEqual(self._status(intent_id), 'cancelled')
        with self.assertRaises(CollectError):
            mark_paid(self.connection, intent_id)

    def test_refund_auto_sous_seuil_ticket_au_dela(self) -> None:
        small = create_intent(self.connection, 'v1', 'invoice', 3.0)
        to_issued(self.connection, small, 'F-1')
        to_sent(self.connection, small)
        mark_paid(self.connection, small)
        result = request_refund(self.connection, POLICY, small)
        self.assertTrue(result['auto'])
        self.assertIsNotNone(result['refund_id'])
        big = create_intent(self.connection, 'v1', 'invoice', 29.0)
        to_issued(self.connection, big, 'F-2')
        to_sent(self.connection, big)
        mark_paid(self.connection, big)
        result = request_refund(self.connection, POLICY, big)
        self.assertFalse(result['auto'])
        self.assertIsNone(result['refund_id'])
        unpaid = create_intent(self.connection, 'v1', 'invoice', 1.0)
        with self.assertRaises(CollectError):
            request_refund(self.connection, POLICY, unpaid)

    def test_canary_marqué(self) -> None:
        intent_id = create_canary(self.connection, 'v1', 'stripe-test')
        envelope = json.loads(
            self.connection.execute(
                'SELECT receipt_json, kind, amount_eur FROM transactions'
                ' WHERE id=?',
                (intent_id,),
            ).fetchone()[0]
        )
        row = self.connection.execute(
            'SELECT kind, amount_eur FROM transactions WHERE id=?',
            (intent_id,),
        ).fetchone()
        self.assertEqual(tuple(row), ('canary', 1.0))
        self.assertTrue(envelope['canary'])
        self.assertEqual(envelope['rail'], 'stripe-test')


if __name__ == '__main__':
    unittest.main()
