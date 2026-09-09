#!/usr/bin/env python3
"""Rail Stripe : requêtes, erreurs typées, webhooks vérifiés (mockés)."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.collect.rails import (  # noqa: E402
    RailError,
    StripeRail,
    stripe_keys,
)

KEY = 'sk_test_' + '0' * 24  # fausse clé mockée (construite pour éviter push-protection)
WHSEC = 'whsec_' + 'test_secret'  # faux secret mocké


def _response(payload: dict, status: int = 200):
    body = json.dumps(payload).encode('utf-8')
    response = mock.MagicMock()
    response.read.return_value = body
    response.status = status
    context = mock.MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


def _signed(body: bytes, timestamp: int = 1700000000) -> str:
    signed = f'{timestamp}.'.encode() + body
    digest = hmac.new(WHSEC.encode(), signed, hashlib.sha256).hexdigest()
    return f't={timestamp},v1={digest}'


class RailTests(unittest.TestCase):
    def test_cles_depuis_sidecar(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / 'secrets').mkdir()
            (root / 'secrets/stripe-test.key').write_text(
                'sk_test_dummy\n', encoding='utf-8'
            )
            (root / 'secrets/stripe-webhook-test.key').write_text(
                'whsec_dummy\n', encoding='utf-8'
            )
            key, whsec = stripe_keys('test', root)
            self.assertEqual((key, whsec), ('sk_test_dummy', 'whsec_dummy'))
            self.assertEqual(stripe_keys('live', root), ('', ''))
        with self.assertRaises(RailError):
            stripe_keys('prod', Path('/tmp'))

    def test_mode_test_refuse_cle_live(self) -> None:
        with self.assertRaises(RailError):
            StripeRail('sk_live_abc', mode='test')
        with self.assertRaises(RailError):
            StripeRail(KEY, mode='live')
        with self.assertRaises(RailError):
            StripeRail(KEY, mode='prod')
        rail = StripeRail(KEY, mode='test')
        self.assertEqual(rail.mode, 'test')

    def test_create_payment_intent(self) -> None:
        rail = StripeRail(KEY)
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 'pi_1', 'status': 'succeeded'}),
        ) as mocked:
            result = rail.create_payment_intent(
                1.0,
                description='canary',
                idempotency_key='int_canary_1',
            )
        self.assertEqual(result['id'], 'pi_1')
        request = mocked.call_args[0][0]
        self.assertIn('/v1/payment_intents', request.full_url)
        self.assertEqual(request.get_header('Idempotency-key'), 'int_canary_1')
        self.assertTrue(
            request.get_header('Authorization').startswith('Basic ')
        )
        with self.assertRaises(RailError):
            rail.create_payment_intent(0)

    def test_get_et_refund(self) -> None:
        rail = StripeRail(KEY)
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 'pi_1', 'status': 'succeeded'}),
        ) as mocked:
            rail.get_payment_intent('pi_1')
        self.assertIn(
            '/v1/payment_intents/pi_1', mocked.call_args[0][0].full_url
        )
        with self.assertRaises(RailError):
            rail.get_payment_intent('ch_1')
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 're_1', 'status': 'succeeded'}),
        ) as mocked:
            result = rail.refund('pi_1', 1.0, idempotency_key='rf_1')
        self.assertEqual(result['id'], 're_1')
        self.assertIn('/v1/refunds', mocked.call_args[0][0].full_url)

    def test_erreurs_typees(self) -> None:
        rail = StripeRail(KEY)
        error = urllib.error.HTTPError(
            'https://api.stripe.com/v1/payment_intents',
            401,
            'Unauthorized',
            {},
            None,  # type: ignore[arg-type]
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(RailError, '^AUTH'):
                rail.create_payment_intent(1.0)
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('dns'),
        ):
            with self.assertRaisesRegex(RailError, '^NETWORK'):
                rail.create_payment_intent(1.0)

    def test_webhook_verifie(self) -> None:
        rail = StripeRail(KEY, WHSEC)
        body = json.dumps({'id': 'evt_1', 'type': 'x'}).encode()
        event = rail.parse_webhook(body, _signed(body), now=1700000000.0)
        self.assertEqual(event['id'], 'evt_1')
        with self.assertRaisesRegex(RailError, '^SIGNATURE'):
            rail.parse_webhook(body, 't=1700000000,v1=00', now=1700000000.0)
        with self.assertRaisesRegex(RailError, '^STALE'):
            rail.parse_webhook(body, _signed(body), now=1700009999.0)
        with self.assertRaisesRegex(RailError, '^SIGNATURE'):
            rail.parse_webhook(body, 'nonsense', now=1700000000.0)
        no_secret = StripeRail(KEY)
        with self.assertRaisesRegex(RailError, '^SIGNATURE'):
            no_secret.parse_webhook(body, _signed(body), now=1700000000.0)


if __name__ == '__main__':
    unittest.main()
