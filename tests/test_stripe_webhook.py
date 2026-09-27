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
from serge.db.boot import init_schema  # noqa: E402

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

    def test_abonnement_et_facture_liee(self) -> None:
        event = {
            'type': 'customer.subscription.updated',
            'data': {
                'object': {
                    'id': 'sub_abc',
                    'status': 'active',
                    'current_period_end': 1800000000,
                    'items': {
                        'data': [{'price': {'unit_amount': 2900}}],
                    },
                }
            },
        }
        out = apply_event(self.conn, event)
        self.assertEqual(out['status'], 'ok')
        row = self.conn.execute(
            'SELECT amount_eur, status FROM subscriptions'
            " WHERE external_id='sub_abc'"
        ).fetchone()
        self.assertEqual(row[0], 29.0)
        self.assertEqual(row[1], 'active')
        paid = apply_event(
            self.conn,
            {
                'type': 'invoice.paid',
                'data': {
                    'object': {
                        'id': 'in_1',
                        'subscription': 'sub_abc',
                        'payment_intent': 'pi_abo1',
                        'amount_paid': 2900,
                    }
                },
            },
        )
        self.assertEqual(paid['status'], 'ok')
        tx = self.conn.execute(
            "SELECT status FROM transactions WHERE intent_id='pi_abo1'"
        ).fetchone()
        self.assertEqual(tx[0], 'paid')
        lien = self.conn.execute(
            'SELECT last_transaction_id FROM subscriptions'
            " WHERE external_id='sub_abc'"
        ).fetchone()[0]
        self.assertTrue(lien)

    def _abo(self, metadata: dict | None = None, price_md: dict | None = None):
        price: dict = {'unit_amount': 1500}
        if price_md is not None:
            price['metadata'] = price_md
        objet: dict = {
            'id': 'sub_v',
            'status': 'active',
            'items': {'data': [{'price': price}]},
        }
        if metadata is not None:
            objet['metadata'] = metadata
        return apply_event(
            self.conn,
            {
                'type': 'customer.subscription.created',
                'data': {'object': objet},
            },
        )

    def _venture_de(self, external: str) -> str:
        return self.conn.execute(
            'SELECT venture_id FROM subscriptions WHERE external_id=?',
            (external,),
        ).fetchone()[0]

    def test_abonnement_rattache_au_business_du_prix(self) -> None:
        self._abo(price_md={'venture_id': 'v1'})
        self.assertEqual(self._venture_de('sub_v'), 'v1')
        paid = apply_event(
            self.conn,
            {
                'type': 'invoice.paid',
                'data': {
                    'object': {
                        'id': 'in_v',
                        'subscription': 'sub_v',
                        'payment_intent': 'pi_v',
                        'amount_paid': 1500,
                    }
                },
            },
        )
        self.assertEqual(paid['status'], 'ok')
        tx = self.conn.execute(
            "SELECT venture_id FROM transactions WHERE intent_id='pi_v'"
        ).fetchone()
        self.assertEqual(tx[0], 'v1')

    def test_abonnement_sans_business_est_signale(self) -> None:
        self._abo(metadata={'venture_id': 'inconnu'})
        self.assertEqual(self._venture_de('sub_v'), '')
        types = [
            row[0]
            for row in self.conn.execute('SELECT type FROM events').fetchall()
        ]
        self.assertEqual(types.count('collect.subscription_unattached'), 1)
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v2','t','t')"
        )
        self._abo(metadata={'venture_id': 'v2'})
        self.assertEqual(self._venture_de('sub_v'), 'v2')

    def test_business_rattache_jamais_remplace(self) -> None:
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v2','t','t')"
        )
        self._abo(metadata={'venture_id': 'v1'})
        self._abo(metadata={'venture_id': 'v2'})
        self.assertEqual(self._venture_de('sub_v'), 'v1')


if __name__ == '__main__':
    unittest.main()
