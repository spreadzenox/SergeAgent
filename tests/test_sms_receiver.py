#!/usr/bin/env python3
"""SMS receiver: auth, envelope translation, rate limit, broker ingest."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import closing
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402
from serge.sms import SmsInbox  # noqa: E402
from serge.sms.receiver import (  # noqa: E402
    Handler,
    Journal,
    RateLimiter,
    SmsReceiverError,
    check_auth,
    ingest_payload,
    normalize_envelope,
    read_limits,
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
            limits=(60, 10),
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
        vu = self.inbox.messages(limite=1)
        self.assertEqual(vu[0]['expediteur'], '+33600000001')
        self.assertIn('482931', vu[0]['corps'])

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
        limiter, limits = RateLimiter(), (100, 2)
        self.assertTrue(limiter.allow('a', limits, now=1000.0))
        self.assertTrue(limiter.allow('a', limits, now=1001.0))
        self.assertFalse(limiter.allow('a', limits, now=1002.0))
        self.assertTrue(limiter.allow('b', limits, now=1002.0))
        self.assertTrue(limiter.allow('a', limits, now=1061.0))

    def test_global_rate_limit(self) -> None:
        limiter, limits = RateLimiter(), (2, 100)
        self.assertTrue(limiter.allow('a', limits, now=1000.0))
        self.assertTrue(limiter.allow('b', limits, now=1001.0))
        self.assertFalse(limiter.allow('c', limits, now=1002.0))

    def test_plafonds_lus_dans_la_policy_en_vigueur(self) -> None:
        # Le chiffre changé dans Mission Control vaut pour le SMS suivant.
        canon = Path(self.tmp.name) / 'serge.db'
        with closing(open_db(canon)) as conn:
            conn.commit()
        self.assertEqual(read_limits(canon), (60, 10))
        with closing(open_db(canon)) as conn:
            set_setting(conn, 'quotas.sms_per_sender_per_min', 1, 'mc')
            conn.commit()
        limits = read_limits(canon)
        self.assertEqual(limits, (60, 1))
        limiter = RateLimiter()
        self.assertTrue(limiter.allow('a', limits, now=1000.0))
        self.assertFalse(limiter.allow('a', limits, now=1001.0))

    def _canon(self) -> Path:
        canon = Path(self.tmp.name) / 'serge.db'
        with closing(open_db(canon)) as conn:
            conn.commit()
        return canon

    def _journal(self, canon: Path) -> list[tuple[str, dict]]:
        with closing(open_db(canon)) as conn:
            return [
                (str(kind), json.loads(payload))
                for kind, payload in conn.execute(
                    'SELECT type, payload_json FROM events WHERE type LIKE'
                    " 'sms.%' ORDER BY id"
                )
            ]

    def test_un_sms_recu_et_un_refus_sont_au_journal(self) -> None:
        """Mission Control montre qu'un SMS est arrivé, sans son texte ni
        son code, et pourquoi un envoi a été refusé : une fois par raison
        toutes les dix minutes."""
        canon = self._canon()
        journal = Journal(canon)
        raw = json.dumps(
            {
                'id': 'sms_j1',
                'from': 'X',
                'body': 'Ton code : 482931 https://x.com/i/v?t=abc',
                'received_at': '2026-11-20T15:43:00Z',
            }
        ).encode()
        entetes = {
            'X-SMS-Signature': hmac.new(
                SECRET, raw, hashlib.sha256
            ).hexdigest()
        }
        # Le second envoi du même SMS est un doublon : noté une seule fois.
        for _ in range(2):
            ingest_payload(
                raw,
                entetes,
                {},
                secret=SECRET,
                inbox=self.inbox,
                limiter=self.limiter,
                limits=(60, 10),
                journal=journal,
            )
        journal.refuse('missing or invalid auth', now=1000.0)
        journal.refuse('missing or invalid auth', now=1300.0)
        journal.refuse('rate_limited', now=1300.0)
        journal.refuse('missing or invalid auth', now=1700.0)
        vus = self._journal(canon)
        self.assertEqual(
            vus[0],
            ('sms.received', {'de': 'X', 'code': 'oui', 'lien': 'oui'}),
        )
        self.assertEqual([kind for kind, _ in vus[1:]], ['sms.refused'] * 3)
        self.assertIn('pas le bon secret', vus[1][1]['raison'])
        self.assertIn('trop de SMS', vus[2][1]['raison'])
        self.assertNotIn('482931', json.dumps(vus))

    def test_le_serveur_note_ce_qu_il_recoit(self) -> None:
        """Le téléphone frappe à la vraie porte : un mauvais secret est
        refusé et noté avec sa raison, un SMS bien signé est noté reçu."""
        canon = self._canon()
        reglages = mock.patch.multiple(
            Handler,
            secret=SECRET,
            inbox=self.inbox,
            limiter=RateLimiter(),
            canon=canon,
            journal=Journal(canon),
        )
        reglages.start()
        self.addCleanup(reglages.stop)
        serveur = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.addCleanup(serveur.server_close)
        self.addCleanup(serveur.shutdown)
        threading.Thread(target=serveur.serve_forever, daemon=True).start()
        adresse = f'http://127.0.0.1:{serveur.server_port}/hooks/sms'
        corps = json.dumps(
            {
                'id': 'msg_7',
                'phoneNumber': '38698',
                'message': 'Votre code de confirmation : 112233',
                'timestamp': 1795189380000,
            }
        ).encode()

        def poster(jeton: str) -> int:
            requete = urllib.request.Request(
                adresse,
                data=corps,
                headers={
                    'X-SMS-Token': jeton,
                    'Content-Type': 'application/json',
                },
            )
            try:
                with urllib.request.urlopen(requete, timeout=10) as reponse:
                    return int(reponse.status)
            except urllib.error.HTTPError as exc:
                exc.close()
                return int(exc.code)

        with mock.patch('sys.stderr'):
            self.assertEqual(poster('pas-le-bon'), 401)
            self.assertEqual(poster(SECRET.decode()), 200)
        self.assertEqual(
            self._journal(canon),
            [
                (
                    'sms.refused',
                    {
                        'raison': 'jeton absent ou faux : le téléphone'
                        ' n’a pas le bon secret'
                    },
                ),
                (
                    'sms.received',
                    {'de': '38698', 'code': 'oui', 'lien': 'non'},
                ),
            ],
        )


if __name__ == '__main__':
    unittest.main()
