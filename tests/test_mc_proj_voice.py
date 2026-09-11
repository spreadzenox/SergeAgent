#!/usr/bin/env python3
"""Projecteurs P7 Voix : tests unitaires et goldens."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_voice import (  # noqa: E402
    project_bridge_statut,
    project_cdr_appels,
    project_qualite_voix,
)
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.quality import record_call_score  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}


class ProjVoiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-voice-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

        # Simulation ledger
        self.ledger_db = self.root / 'state/voice/voice.db'
        self.ledger = VoiceLedger(self.ledger_db, self.root / 'canon.db')

    def test_cdr_appels(self) -> None:
        with mock.patch(
            'serge.mc.proj_voice.default_ledger_path',
            return_value=self.ledger_db,
        ):
            res0 = project_cdr_appels(self.conn, POLICY, NOW)
            self.assertEqual(res0['total'], 0)
            self.assertEqual(res0['calls'], [])

            # Ajout appel
            res_rec = self.ledger.record_inbound(
                caller='+33612345678', did='+33199887766'
            )
            self.ledger.record_outcome(
                res_rec['cdr_id'],
                outcome='completed',
                duration_s=42,
                recording_path='/tmp/rec.wav',
            )

            res1 = project_cdr_appels(self.conn, POLICY, NOW)
            self.assertEqual(res1['total'], 1)
            call = res1['calls'][0]
            self.assertEqual(call['duration_s'], 42)
            self.assertTrue(call['has_recording'])
            self.assertIn('sig=', call['audio_url'])

    def test_qualite_voix(self) -> None:
        res0 = project_qualite_voix(self.conn, POLICY, NOW)
        self.assertEqual(res0['total_notes'], 0)
        self.assertIsNone(res0['note_moyenne'])

        record_call_score(self.conn, 'cdr_1', 4, ['ok'], False)
        record_call_score(self.conn, 'cdr_2', 5, ['parfait'], False)
        self.conn.commit()

        res1 = project_qualite_voix(self.conn, POLICY, NOW)
        self.assertEqual(res1['total_notes'], 2)
        self.assertEqual(res1['note_moyenne'], 4.5)

    def test_bridge_statut(self) -> None:
        with mock.patch(
            'serge.mc.proj_voice.system_root', return_value=self.root
        ):
            res = project_bridge_statut(self.conn, POLICY, NOW)
            self.assertIn('kill_switch', res)
            self.assertFalse(res['kill_switch'])
            self.assertIn('bridge', res)


if __name__ == '__main__':
    unittest.main()
