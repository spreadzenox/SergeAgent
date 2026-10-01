#!/usr/bin/env python3
"""Infrastructure Voix P7 : purge rétention."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.voice_retention import purger_audio_voix  # noqa: E402


class VoiceRetentionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-retention-')
        self.addCleanup(self.tmp.cleanup)
        self.audio_dir = Path(self.tmp.name) / 'audio'
        self.audio_dir.mkdir(parents=True)

        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def test_purge_fichiers_anciens(self) -> None:
        now = datetime.now(UTC)
        vieux_fichier = self.audio_dir / 'call_vieux.wav'
        vieux_fichier.write_bytes(b'AUDIO_DATA_OLD' * 10)
        vieux_mtime = (now - timedelta(days=40)).timestamp()
        import os

        os.utime(vieux_fichier, (vieux_mtime, vieux_mtime))

        recent_fichier = self.audio_dir / 'call_recent.wav'
        recent_fichier.write_bytes(b'AUDIO_DATA_NEW' * 10)

        res = purger_audio_voix(
            self.conn,
            self.audio_dir,
            retention_jours=30,
            now_iso=now.isoformat(),
        )
        self.assertEqual(res['fichiers_supprimes'], 1)
        self.assertTrue(res['octets_liberes'] > 0)
        self.assertFalse(vieux_fichier.exists())
        self.assertTrue(recent_fichier.exists())

        ev = self.conn.execute(
            "SELECT payload_json FROM events WHERE type='voice.purged'"
        ).fetchone()
        self.assertIsNotNone(ev)


if __name__ == '__main__':
    unittest.main()
