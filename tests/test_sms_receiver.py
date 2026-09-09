#!/usr/bin/env python3
"""SMS receiver: auth, envelope translation, rate limit, broker ingest."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.sms import SmsInbox  # noqa: E402
from serge.sms.receiver import (  # noqa: E402
    RateLimiter,
    SmsReceiverError,
    check_auth,
    ingest_payload,
    normalize_envelope,
)

SECRET = b'0123456789abcdef0123456789abcdef'


def _headers(**items):
    return {key: value for key, value in items.items()}


class SmsReceiverTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.inbox = SmsInbox(Path(self.tmp.name) / 'sms.db')
        self.limiter = RateLimiter()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _ingest(self, obj, *, auth='hmac', query=None):
        raw = json.dumps(obj).encode('utf-8')
        headers = {}
        if auth == 'hmac':
            headers['X-SMS-Signature'] = hmac.new(
                SECRET,
                raw,
                hashlib.sha256,
            ).hexdigest()
        elif auth == 'token':
            headers['X-SMS-Token'] = SECRET.decode()
        return ingest_payload(
            raw,
            headers,
            query or {},
            secret=SECRET,
            inbox=self.inbox,
            limiter=self.limiter,
        )

    def test_canonical_envelope_accepted(self) -> None:
        result = self._ingest(
            {
                'id': 'sms_1',
                'from': '+33600000001',
                'body': 'Votre code : 482931',
                'received_at': '2026-09-09T08:00:00Z',
            }
        )
        self.assertEqual(result['status'], 'accepted')
        self.assertTrue(result['otp_present'])
        self.assertEqual(result['auth'], 'hmac')
        self.assertEqual(self.inbox.latest_otp(), '482931')

    def test_android_app_shape_translated(self) -> None:
        result = self._ingest(
            {
                'id': 'msg_42',
                'phoneNumber': '+33600000002',
                'message': 'Code 112233 pour valider',
                'timestamp': 1786224000000,
            }
        )
        self.assertEqual(result['status'], 'accepted')
        self.assertTrue(result['otp_present'])

    def test_token_header_and_query_param_accepted(self) -> None:
        first = self._ingest(
            {
                'id': 'sms_t1',
                'from': '+33600000003',
                'body': 'code 111111',
                'received_at': '2026-09-09T08:00:00Z',
            },
            auth='token',
        )
        self.assertEqual(first['auth'], 'token')
        second = self._ingest(
            {
                'id': 'sms_t2',
                'from': '+33600000003',
                'body': 'code 222222',
                'received_at': '2026-09-09T08:01:00Z',
            },
            auth='none',
            query={'token': [SECRET.decode()]},
        )
        self.assertEqual(second['status'], 'accepted')

    def test_bad_auth_refused(self) -> None:
        raw = json.dumps({'id': 'x'}).encode()
        with self.assertRaises(SmsReceiverError):
            check_auth(raw, _headers(), {}, SECRET)
        with self.assertRaises(SmsReceiverError):
            check_auth(
                raw,
                _headers(**{'X-SMS-Signature': '0' * 64}),
                {},
                SECRET,
            )
        with self.assertRaises(SmsReceiverError):
            check_auth(raw, _headers(**{'X-SMS-Token': 'nope'}), {}, SECRET)

    def test_unmappable_payload_refused(self) -> None:
        with self.assertRaises(SmsReceiverError):
            normalize_envelope({'hello': 'world'})
        with self.assertRaises(SmsReceiverError):
            normalize_envelope(['not', 'a', 'dict'])

    def test_duplicate_is_idempotent(self) -> None:
        obj = {
            'id': 'sms_dup',
            'from': '+33600000004',
            'body': 'code 333333',
            'received_at': '2026-09-09T08:00:00Z',
        }
        self.assertEqual(self._ingest(obj)['status'], 'accepted')
        self.assertEqual(self._ingest(obj)['status'], 'duplicate')

    def test_response_never_contains_otp(self) -> None:
        result = self._ingest(
            {
                'id': 'sms_priv',
                'from': '+33600000005',
                'body': 'Votre code : 987654',
                'received_at': '2026-09-09T08:00:00Z',
            }
        )
        self.assertNotIn('987654', json.dumps(result))

    def test_rate_limit_per_sender(self) -> None:
        limiter = RateLimiter(sender_per_minute=2, global_per_minute=100)
        self.assertTrue(limiter.allow('a', now=1000.0))
        self.assertTrue(limiter.allow('a', now=1001.0))
        self.assertFalse(limiter.allow('a', now=1002.0))
        self.assertTrue(limiter.allow('b', now=1002.0))
        self.assertTrue(limiter.allow('a', now=1061.0))

    def test_global_rate_limit(self) -> None:
        limiter = RateLimiter(sender_per_minute=100, global_per_minute=2)
        self.assertTrue(limiter.allow('a', now=1000.0))
        self.assertTrue(limiter.allow('b', now=1001.0))
        self.assertFalse(limiter.allow('c', now=1002.0))


if __name__ == '__main__':
    unittest.main()
