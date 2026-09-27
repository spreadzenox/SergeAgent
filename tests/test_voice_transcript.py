#!/usr/bin/env python3
"""Ledger voix : transcript persisté sur clôture S2S."""

from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import VoicePolicy  # noqa: E402

CLI = '+33162000001'
TO = '+33612345678'
TUESDAY_NOON = datetime(2026, 9, 8, 10, 30, tzinfo=UTC)


class VoiceTranscriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        canon = root / 'serge.db'
        conn = __import__('sqlite3').connect(canon)
        init_schema(conn)
        conn.close()
        self.ledger = VoiceLedger(root / 'voice.db', canon_path=canon)
        self.ledger.grant_consent(TO, 'contract')

    def test_clore_dernier_ecrit_transcript(self) -> None:
        policy = VoicePolicy(
            mode='live',
            mandate_outbound_allowed=True,
            mandate_inbound_allowed=True,
            external_actions=True,
            cli_expected=CLI,
            max_calls_per_day=10,
        )
        asked = self.ledger.request_call(
            policy,
            request_id='req_tr',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            now=TUESDAY_NOON,
        )
        self.assertEqual(asked['decision'], 'allowed')
        out = self.ledger.clore_dernier_autorise(
            duration_s=42, transcript='Bonjour, ici Serge.'
        )
        self.assertEqual(out['status'], 'recorded')
        self.assertEqual(out['cdr_id'], asked['cdr_id'])
        row = (
            self.ledger._connect()
            .execute(
                'SELECT outcome, duration_s, transcript FROM calls WHERE cdr_id=?',
                (out['cdr_id'],),
            )
            .fetchone()
        )
        self.assertEqual(row[0], 'completed')
        self.assertEqual(row[1], 42)
        self.assertIn('Serge', row[2])


if __name__ == '__main__':
    unittest.main()
