#!/usr/bin/env python3
"""Séquence E (live-prudent) : canary 1 € test-mode + refund immédiat.

Skippé hors SERGE_ENV=test + SERGE_STRIPE_TEST_KEY (sk_test_). Net 0
(refund systématique). 3 appels Stripe max (création, lecture, refund).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect.intents import (  # noqa: E402
    create_canary,
    mark_paid,
    to_issued,
    to_sent,
)
from serge.collect.rails import StripeRail  # noqa: E402
from serge.testkit import SessionCap, require_live, temp_canon  # noqa: E402


class LiveCollectTests(unittest.TestCase):
    def test_canary_1eur_puis_refund(self) -> None:
        require_live()
        key = os.environ.get('SERGE_STRIPE_TEST_KEY', '').strip()
        if not key.startswith(('sk_test_', 'rk_test_')):
            self.skipTest('SERGE_STRIPE_TEST_KEY (sk_test_/rk_test_) requise')
        cap = SessionCap(4)
        rail = StripeRail(key, mode='test')
        with temp_canon() as (conn, _):
            intent_id = create_canary(conn, 'live-test', 'stripe-test')
            cap.spend('payment_intent.create')
            intent = rail.create_payment_intent(
                1.0,
                description='serge canary E (test-mode, refundé)',
                idempotency_key=f'canary-{intent_id}',
            )
            self.assertEqual(intent['status'], 'succeeded')
            to_issued(conn, intent_id, intent['id'])
            to_sent(conn, intent_id)
            mark_paid(conn, intent_id, {'pi': intent['id']})
            cap.spend('payment_intent.get')
            readback = rail.get_payment_intent(intent['id'])
            self.assertEqual(readback['amount_received'], 100)
            cap.spend('refund.create')
            refund = rail.refund(intent['id'])
            self.assertEqual(refund['status'], 'succeeded')
            conn.commit()


if __name__ == '__main__':
    unittest.main()
