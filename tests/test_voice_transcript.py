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

from serge.coupe_circuit import set_heartbeat  # noqa: E402
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
        set_heartbeat(conn, True)  # Serge est arrêté par défaut
        conn.commit()
        conn.close()
        self.ledger = VoiceLedger(root / 'voice.db', canon_path=canon)
        self.ledger.grant_consent(TO, 'contract')

    def test_l_appel_ferme_garde_sa_transcription(self) -> None:
        policy = VoicePolicy(
            mode='live',
            mandate_outbound_allowed=True,
            mandate_inbound_allowed=True,
            external_actions=True,
            cli_expected=CLI,
        )
        asked = self.ledger.request_call(
            policy,
            request_id='t1.1',
            to_e164=TO,
            cli=CLI,
            purpose='contract',
            task_id='t1',
            now=TUESDAY_NOON,
        )
        self.assertEqual(asked['decision'], 'allowed')
        out = self.ledger.record_outcome(
            asked['cdr_id'],
            outcome='completed',
            duration_s=42,
            transcript='Serge : Bonjour, ici Serge.',
        )
        self.assertEqual(out['status'], 'recorded')
        # Le journal retrouve l'appel par son envoi (confirmer un envoi).
        self.assertEqual(
            self.ledger.calls_for_task('t1'),
            [
                {
                    'request_id': 't1.1',
                    'decision': 'allowed',
                    'reason': 'allowed',
                    'outcome': 'completed',
                    'cdr_id': asked['cdr_id'],
                }
            ],
        )
        row = (
            self.ledger._connect()
            .execute(
                'SELECT outcome, duration_s, transcript FROM calls WHERE cdr_id=?',
                (asked['cdr_id'],),
            )
            .fetchone()
        )
        self.assertEqual(
            tuple(row), ('completed', 42, 'Serge : Bonjour, ici Serge.')
        )


if __name__ == '__main__':
    unittest.main()
