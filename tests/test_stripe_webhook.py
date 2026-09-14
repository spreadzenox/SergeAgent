#!/usr/bin/env python3
"""Webhook Stripe : URL d’instance, HMAC, passage paid."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect import create_intent, to_issued  # noqa: E402
from serge.collect.rails import RailError  # noqa: E402
from serge.collect.webhook import (  # noqa: E402
    apply_event,
    installer_hint,
    public_webhook_url,
    verify_event,
)
from serge.db.schema import init_schema  # noqa: E402

WHSEC = 'whsec_test_secret'


def _signed(
    body: bytes, secret: str = WHSEC, timestamp: int = 1700000000
) -> str:
    digest = hmac.new(
        secret.encode(), f'{timestamp}.'.encode() + body, hashlib.sha256
    ).hexdigest()
    return f't={timestamp},v1={digest}'


class StripeWebhookTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_url_uses_instance_hostname(self) -> None:
        self.assertEqual(
            public_webhook_url('jpesquet.tech'),
            'https://jpesquet.tech/hooks/stripe',
        )
        self.assertEqual(
            public_webhook_url('https://Autre.Example.net/'),
            'https://autre.example.net/hooks/stripe',
        )
        self.assertIn(
            'https://serge.example.net/hooks/stripe',
            installer_hint('serge.example.net'),
        )

    def test_verify_live_then_test(self) -> None:
        body = json.dumps({'id': 'evt_1', 'type': 'ping'}).encode()
        mode, event = verify_event(
            body,
            _signed(body, 'whsec_live'),
            {'live': 'whsec_live', 'test': WHSEC},
            now=1700000000.0,
        )
        self.assertEqual(mode, 'live')
        self.assertEqual(event['id'], 'evt_1')
        mode, _event = verify_event(
            body,
            _signed(body),
            {'live': 'whsec_other', 'test': WHSEC},
            now=1700000000.0,
        )
        self.assertEqual(mode, 'test')
        with self.assertRaises(RailError):
            verify_event(
                body, _signed(body), {'test': 'whsec_nope'}, now=1700000000.0
            )

    def test_apply_marks_paid_and_idempotent(self) -> None:
        tx = create_intent(
            self.conn, 'v1', 'invoice', 12.0, intent_key='pi_abc123'
        )
        to_issued(self.conn, tx, 'F-1')
        event = {
            'id': 'evt_paid',
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_abc123'}},
        }
        first = apply_event(self.conn, event)
        self.assertEqual(first['status'], 'ok')
        second = apply_event(self.conn, event)
        self.assertTrue(second.get('already'))
        status = self.conn.execute(
            'SELECT status FROM transactions WHERE id=?', (tx,)
        ).fetchone()[0]
        self.assertEqual(status, 'paid')

    def test_unmatched_and_ignored(self) -> None:
        event = {
            'type': 'payment_intent.succeeded',
            'data': {'object': {'id': 'pi_unknown'}},
        }
        self.assertEqual(apply_event(self.conn, event)['status'], 'unmatched')
        self.assertEqual(
            apply_event(self.conn, {'type': 'customer.created'})['status'],
            'ignored',
        )

    def test_checkout_session_uses_payment_intent(self) -> None:
        tx = create_intent(
            self.conn, 'v1', 'invoice', 5.0, intent_key='pi_sess'
        )
        to_issued(self.conn, tx, 'F-2')
        event = {
            'id': 'evt_sess',
            'type': 'checkout.session.completed',
            'data': {'object': {'payment_intent': 'pi_sess'}},
        }
        self.assertEqual(apply_event(self.conn, event)['status'], 'ok')


if __name__ == '__main__':
    unittest.main()
