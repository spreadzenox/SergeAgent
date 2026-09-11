#!/usr/bin/env python3
"""Infrastructure Voix P7 : tests unitaires signedlinks HMAC et purge rétention."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.signedlinks import signer_url, verifier_url  # noqa: E402
from serge.mc.voice_retention import purger_audio_voix  # noqa: E402


class SignedLinksTests(unittest.TestCase):
    def test_signature_et_verification_ok(self) -> None:
        secret = 'cle-secrete-owner-42'
        url_initiale = '/owner/api/voice/audio?cdr=cdr_123'
        t0 = 1000.0

        url_signee = signer_url(
            url_initiale, secret, ttl_s=60, now_fn=lambda: t0
        )
        self.assertIn('exp=1060', url_signee)
        self.assertIn('sig=', url_signee)

        # Vérification valide au temps t0 + 30s
        self.assertTrue(
            verifier_url(url_signee, secret, now_fn=lambda: t0 + 30)
        )

        # Rejet si expiré au temps t0 + 61s
        self.assertFalse(
            verifier_url(url_signee, secret, now_fn=lambda: t0 + 61)
        )

        # Rejet si mauvais secret
        self.assertFalse(
            verifier_url(url_signee, 'mauvais-secret', now_fn=lambda: t0)
        )

        # Rejet si altération de paramètre
        url_alteree = url_signee.replace('cdr_123', 'cdr_999')
        self.assertFalse(verifier_url(url_alteree, secret, now_fn=lambda: t0))


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
