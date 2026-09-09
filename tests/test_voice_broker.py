#!/usr/bin/env python3
"""Voice broker: fail-closed policy, quotas, consent, idempotency."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from zoneinfo import ZoneInfo

from serge.voice import (  # noqa: E402
    VoiceBrokerDenied,
    VoiceLedger,
    VoicePolicy,
    easter_sunday,
    french_holidays,
    within_legal_hours,
)

CLI = '+33162000001'
TO = '+33612345678'

# Tuesday 2026-09-08 10:30 UTC = 12:30 Paris (CEST), inside window.
TUESDAY_NOON = datetime(2026, 9, 8, 10, 30, tzinfo=UTC)


def _policy(**overrides) -> VoicePolicy:
    base = {
        'mode': 'live',
        'mandate_outbound_allowed': True,
        'mandate_inbound_allowed': True,
        'external_actions': True,
        'kill_switch': False,
        'cli_expected': CLI,
        'max_calls_per_day': 50,
    }
    base.update(overrides)
    return VoicePolicy(**base)


class VoiceBrokerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = VoiceLedger(
            Path(self.tmp.name) / 'voice.db',
            Path(self.tmp.name) / 'canon.db',
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _allowed_call(self, to: str = TO, request_id: str = 'req_1') -> dict:
        self.ledger.grant_consent(to, 'contract')
        return self.ledger.request_call(
            _policy(),
            request_id=request_id,
            to_e164=to,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )

    def test_easter_and_movable_holidays(self) -> None:
        self.assertEqual(easter_sunday(2025), date(2025, 4, 20))
        self.assertEqual(easter_sunday(2026), date(2026, 4, 5))
        holidays = french_holidays(2026)
        self.assertIn(date(2026, 4, 6), holidays)  # Easter Monday
        self.assertIn(date(2026, 5, 14), holidays)  # Ascension
        self.assertIn(date(2026, 5, 25), holidays)  # Whit Monday
        self.assertIn(date(2026, 5, 1), holidays)
        self.assertIn(date(2026, 7, 14), holidays)

    def test_legal_hours_windows(self) -> None:
        paris = ZoneInfo('Europe/Paris')
        self.assertTrue(within_legal_hours(TUESDAY_NOON.astimezone(paris)))
        early = datetime(2026, 9, 8, 5, 0, tzinfo=UTC)  # 07:00 Paris
        self.assertFalse(within_legal_hours(early.astimezone(paris)))
        lunch = datetime(2026, 9, 8, 11, 30, tzinfo=UTC)  # 13:30 Paris
        self.assertFalse(within_legal_hours(lunch.astimezone(paris)))
        saturday = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)
        self.assertFalse(within_legal_hours(saturday.astimezone(paris)))
        may_day = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
        self.assertFalse(within_legal_hours(may_day.astimezone(paris)))

    def test_happy_path_allowed(self) -> None:
        result = self._allowed_call()
        self.assertEqual(result['decision'], 'allowed')
        self.assertTrue(result['cdr_id'].startswith('cdr_'))
        self.assertFalse(result['duplicate'])

    def test_sandbox_killswitch_external_mandate_deny(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        for overrides, reason in (
            ({'mode': 'sandbox'}, 'sandbox_no_outbound'),
            ({'kill_switch': True}, 'kill_switch_active'),
            ({'external_actions': False}, 'external_actions_disabled'),
            ({'mandate_outbound_allowed': False}, 'mandate_deny'),
        ):
            result = self.ledger.request_call(
                _policy(**overrides),
                request_id=f'req_{reason}',
                to_e164=TO,
                cli=CLI,
                purpose='contract',
                now=TUESDAY_NOON,
            )
            self.assertEqual(result['decision'], 'denied', overrides)
            self.assertEqual(result['reason'], reason)

    def test_cli_must_be_locked_npv(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        result = self.ledger.request_call(
            _policy(),
            request_id='req_cli',
            to_e164=TO,
            cli='+33600000001',
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['reason'], 'cli_not_locked_npv')

    def test_consent_required_and_revocable(self) -> None:
        result = self.ledger.request_call(
            _policy(),
            request_id='req_noconsent',
            to_e164=TO,
            cli=CLI,
            purpose='prospection',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['reason'], 'no_consent_or_contract')
        self.ledger.grant_consent(TO, 'consent')
        result = self.ledger.request_call(
            _policy(),
            request_id='req_consented',
            to_e164=TO,
            cli=CLI,
            purpose='prospection',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['decision'], 'allowed')
        self.ledger.revoke_consent(TO)
        self.ledger.record_outcome(result['cdr_id'], outcome='completed')
        result = self.ledger.request_call(
            _policy(),
            request_id='req_revoked',
            to_e164=TO,
            cli=CLI,
            purpose='prospection',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['reason'], 'no_consent_or_contract')

    def test_blocklist_denies(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        self.ledger.block(TO, 'bloctel')
        result = self.ledger.request_call(
            _policy(),
            request_id='req_blocked',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['reason'], 'blocklisted')
        self.ledger.unblock(TO)
        result = self.ledger.request_call(
            _policy(),
            request_id='req_unblocked',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(result['decision'], 'allowed')

    def test_outside_hours_denies(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        night = datetime(2026, 9, 8, 5, 0, tzinfo=UTC)
        result = self.ledger.request_call(
            _policy(),
            request_id='req_night',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=night,
        )
        self.assertEqual(result['reason'], 'outside_legal_hours')

    def test_recipient_quota_4_per_30d(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        for index in range(4):
            result = self.ledger.request_call(
                _policy(),
                request_id=f'req_q{index}',
                to_e164=TO,
                cli=CLI,
                purpose='contract',
                now=TUESDAY_NOON,
            )
            self.assertEqual(result['decision'], 'allowed', index)
            self.ledger.record_outcome(result['cdr_id'], outcome='completed')
        fifth = self.ledger.request_call(
            _policy(),
            request_id='req_q4',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(fifth['reason'], 'recipient_quota_4_per_30d')

    def test_daily_quota(self) -> None:
        policy = _policy(max_calls_per_day=1)
        self.ledger.grant_consent(TO, 'contract')
        self.ledger.grant_consent('+33612345679', 'contract')
        first = self.ledger.request_call(
            policy,
            request_id='req_d1',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(first['decision'], 'allowed')
        self.ledger.record_outcome(first['cdr_id'], outcome='completed')
        second = self.ledger.request_call(
            policy,
            request_id='req_d2',
            to_e164='+33612345679',
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(second['reason'], 'daily_quota_exceeded')

    def test_concurrent_same_recipient_denies(self) -> None:
        first = self._allowed_call()
        self.assertEqual(first['decision'], 'allowed')
        second = self.ledger.request_call(
            _policy(),
            request_id='req_concurrent',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(second['reason'], 'already_in_progress')

    def test_idempotent_replay_and_divergent_replay(self) -> None:
        first = self._allowed_call()
        replay = self.ledger.request_call(
            _policy(),
            request_id='req_1',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertTrue(replay['duplicate'])
        self.assertEqual(replay['cdr_id'], first['cdr_id'])
        with self.assertRaises(VoiceBrokerDenied):
            self.ledger.request_call(
                _policy(),
                request_id='req_1',
                to_e164='+33699999999',
                cli=CLI,
                purpose='contract',
                now=TUESDAY_NOON,
            )

    def test_invalid_inputs_deny(self) -> None:
        self.ledger.grant_consent(TO, 'contract')
        bad_number = self.ledger.request_call(
            _policy(),
            request_id='req_badnum',
            to_e164='not-a-number',
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(bad_number['reason'], 'invalid_recipient_e164')
        bad_purpose = self.ledger.request_call(
            _policy(),
            request_id='req_badpurpose',
            to_e164=TO,
            cli=CLI,
            purpose='spam',
            now=TUESDAY_NOON,
        )
        self.assertEqual(bad_purpose['reason'], 'invalid_purpose')

    def test_claim_outbound_for_agi(self) -> None:
        allowed = self._allowed_call()
        claim = self.ledger.claim_outbound(TO, now=TUESDAY_NOON)
        self.assertIsNotNone(claim)
        assert claim is not None
        self.assertEqual(claim['cdr_id'], allowed['cdr_id'])
        self.assertIsNone(self.ledger.claim_outbound(TO, now=TUESDAY_NOON))

    def test_db_is_owner_only(self) -> None:
        db_path = Path(self.tmp.name) / 'voice.db'
        self.assertEqual(oct(db_path.stat().st_mode & 0o777), '0o600')

    def test_doctor_counts(self) -> None:
        self._allowed_call()
        info = self.ledger.doctor()
        self.assertEqual(info['status'], 'ok')
        self.assertEqual(info['calls'], 1)
        self.assertEqual(info['consents'], 1)

    def test_consentement_visible_des_guards(self) -> None:
        import sqlite3

        from serge.guards import check

        self.ledger.grant_consent(TO, 'contract')
        policy = {
            'consent': {'opt_in_channels': ['voice']},
            'calling_zones': {
                'default': 'FR',
                'FR': {'contact_per_30d': 4},
            },
        }
        canon = sqlite3.connect(Path(self.tmp.name) / 'canon.db')
        try:
            verdict = check(
                canon,
                policy,
                {
                    'channel': 'voice',
                    'subject': TO,
                    'idempotency_key': 'k-coh',
                },
                TUESDAY_NOON.isoformat(),
            )
        finally:
            canon.close()
        self.assertTrue(verdict.allowed)


if __name__ == '__main__':
    unittest.main()
