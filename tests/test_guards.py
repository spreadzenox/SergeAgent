#!/usr/bin/env python3
"""Guards: idempotence, blocklist, consent, quota 30j, fenêtres voix."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.guards import Reason, check  # noqa: E402
from serge.policy import load_policy  # noqa: E402
from serge.privacy import subject_hash  # noqa: E402

# Mardi 2026-09-08 12:30 Paris (fenêtre légale), dimanche 06 (fermé).
TUESDAY = '2026-09-08T10:30:00+00:00'
SUNDAY = '2026-09-06T10:30:00+00:00'

POLICY = {
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}


def _digest(subject: str) -> str:
    return subject_hash(subject)


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(':memory:')
        init_schema(self.connection)
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def _touch(self, key: str, contact: str, created: str) -> None:
        self.connection.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (key, 'c1', contact, 'email', 'sent', key, created, created),
        )
        self.connection.commit()

    def _consent(self, channel: str, subject: str, revoked: str = '') -> None:
        self.connection.execute(
            'INSERT INTO consents(id, channel, subject_hash, basis,'
            ' granted_at, revoked_at) VALUES(?,?,?,?,?,?)',
            (
                f'{channel}:{subject}',
                channel,
                _digest(subject),
                'contract',
                TUESDAY,
                revoked,
            ),
        )
        self.connection.commit()

    def _block(self, channel: str, subject: str) -> None:
        self.connection.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            ' added_at) VALUES(?,?,?,?,?)',
            (
                f'{channel}:{subject}',
                channel,
                _digest(subject),
                'owner',
                TUESDAY,
            ),
        )
        self.connection.commit()

    def test_ok_email_sans_consentement(self) -> None:
        verdict = check(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'subject': 'Lead@Example.com',
                'idempotency_key': 'k-ok',
                'contact_id': 'p1',
            },
            TUESDAY,
        )
        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.reason, Reason.OK)

    def test_duplicata_idempotent(self) -> None:
        self._touch('k-dup', 'p1', TUESDAY)
        verdict = check(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'subject': 'a@b.c',
                'idempotency_key': 'k-dup',
            },
            TUESDAY,
        )
        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.reason, Reason.DUPLICATE_IDEMPOTENT)
        self.assertTrue(verdict.duplicate)

    def test_blocklist_canal_et_globale(self) -> None:
        self._block('email', 'spam@x.io')
        self._block('*', 'global@y.io')
        for subject in ('spam@x.io', 'global@y.io'):
            verdict = check(
                self.connection,
                POLICY,
                {
                    'channel': 'email',
                    'subject': subject,
                    'idempotency_key': f'k-{subject}',
                },
                TUESDAY,
            )
            self.assertEqual(verdict.reason, Reason.BLOCKLISTED, subject)
            self.assertFalse(verdict.allowed)

    def test_consentement_opt_in_voix(self) -> None:
        action = {
            'channel': 'voice',
            'subject': '+33612345678',
            'idempotency_key': 'k-v',
        }
        self.assertEqual(
            check(self.connection, POLICY, action, TUESDAY).reason,
            Reason.NO_CONSENT,
        )
        self._consent('voice', '+33612345678')
        self.assertTrue(
            check(self.connection, POLICY, action, TUESDAY).allowed
        )
        self._consent('voice', '+33699999999', revoked=TUESDAY)
        action2 = dict(action)
        action2['subject'] = '+33699999999'
        action2['idempotency_key'] = 'k-v2'
        self.assertEqual(
            check(self.connection, POLICY, action2, TUESDAY).reason,
            Reason.NO_CONSENT,
        )

    def test_quota_contact_30j(self) -> None:
        for index in range(4):
            self._touch(f'k-q{index}', 'p9', TUESDAY)
        verdict = check(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'subject': 'q@x.io',
                'idempotency_key': 'k-q9',
                'contact_id': 'p9',
            },
            TUESDAY,
        )
        self.assertEqual(verdict.reason, Reason.QUOTA_CONTACT_30D)
        self.assertTrue(verdict.retry_at)
        # Touches anciennes (> 30j) : ne comptent pas.
        self._touch('k-old', 'p8', '2026-01-01T00:00:00+00:00')
        verdict = check(
            self.connection,
            POLICY,
            {
                'channel': 'email',
                'subject': 'o@x.io',
                'idempotency_key': 'k-o8',
                'contact_id': 'p8',
            },
            TUESDAY,
        )
        self.assertTrue(verdict.allowed)

    def test_fenetres_voix(self) -> None:
        self._consent('voice', '+33612345678')
        action = {
            'channel': 'voice',
            'subject': '+33612345678',
            'idempotency_key': 'k-w',
        }
        self.assertTrue(
            check(self.connection, POLICY, action, TUESDAY).allowed
        )
        action2 = dict(action)
        action2['idempotency_key'] = 'k-w2'
        self.assertEqual(
            check(self.connection, POLICY, action2, SUNDAY).reason,
            Reason.OUTSIDE_WINDOW,
        )

    def test_canal_inconnu_refuse(self) -> None:
        verdict = check(
            self.connection,
            POLICY,
            {
                'channel': 'pigeon',
                'subject': 'x',
                'idempotency_key': 'k-p',
            },
            TUESDAY,
        )
        self.assertEqual(verdict.reason, Reason.UNKNOWN_CHANNEL)
        self.assertFalse(verdict.allowed)

    def test_policy_reelle_fournit_consent_et_cap(self) -> None:
        policy = load_policy()
        self.assertIn('voice', policy['consent']['opt_in_channels'])
        self.assertEqual(policy['calling_zones']['FR']['contact_per_30d'], 4)
        verdict = check(
            self.connection,
            policy,
            {
                'channel': 'email',
                'subject': 'real@x.io',
                'idempotency_key': 'k-real',
            },
            TUESDAY,
        )
        self.assertTrue(verdict.allowed)


if __name__ == '__main__':
    unittest.main()
