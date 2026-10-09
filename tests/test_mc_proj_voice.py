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

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_voice import (  # noqa: E402
    project_bridge_statut,
    project_cdr_appels,
    project_journal_voix,
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
            self.assertTrue(
                call['audio_url'].startswith('/owner/api/voice/audio?cdr=')
            )

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
        set_heartbeat(self.conn, True)
        res = project_bridge_statut(self.conn, POLICY, NOW)
        self.assertFalse(res['kill_switch'])
        self.assertIn('bridge', res)

    def test_serge_arrete_visible_dans_le_statut(self) -> None:
        res = project_bridge_statut(self.conn, POLICY, NOW)
        self.assertTrue(res['kill_switch'])  # arrêté par défaut

    def test_les_journaux_du_serveur_se_lisent_dans_mission_control(
        self,
    ) -> None:
        """Le journal du pont et d'Asterisk, et le fichier d'Asterisk : un
        journal illisible le dit sans casser la page."""
        fichier = self.root / 'logs/asterisk/messages'
        fichier.parent.mkdir(parents=True)
        fichier.write_text(
            ''.join(f'[ligne {i}]\n' for i in range(200)), encoding='utf-8'
        )
        appels = []

        def journalctl(args, **_kw):
            appels.append(args)
            unit = args[args.index('--unit') + 1]
            if unit == 'serge-asterisk.service':
                return mock.Mock(
                    returncode=1, stdout='', stderr='Failed to open journal'
                )
            return mock.Mock(
                returncode=0,
                stdout='voice-s2s: appel\nvoice-s2s: erreur imprévue\n',
                stderr='',
            )

        with (
            mock.patch.dict(
                'os.environ', {'SERGE_SYSTEM_ROOT': str(self.root)}
            ),
            mock.patch(
                'serge.mc.proj_voice.shutil.which', return_value='/bin/x'
            ),
            mock.patch(
                'serge.mc.proj_voice.subprocess.run', side_effect=journalctl
            ),
        ):
            blocs = project_journal_voix(self.conn, POLICY, NOW)['blocs']
        self.assertEqual(
            [(b['titre'], b['erreur']) for b in blocs],
            [
                ('Pont vocal', ''),
                (
                    'Asterisk et le secours tour par tour',
                    'Failed to open journal',
                ),
                ('Asterisk, fichier messages', ''),
            ],
        )
        self.assertEqual(
            blocs[0]['lignes'],
            ['voice-s2s: appel', 'voice-s2s: erreur imprévue'],
        )
        self.assertEqual(len(blocs[2]['lignes']), 150)
        self.assertEqual(blocs[2]['lignes'][-1], '[ligne 199]')
        self.assertIn('--user', appels[0])

    def test_sans_journalctl_la_section_le_dit(self) -> None:
        with (
            mock.patch.dict(
                'os.environ', {'SERGE_SYSTEM_ROOT': str(self.root)}
            ),
            mock.patch('serge.mc.proj_voice.shutil.which', return_value=None),
        ):
            blocs = project_journal_voix(self.conn, POLICY, NOW)['blocs']
        self.assertEqual(
            [b['erreur'] for b in blocs],
            [
                'journalctl absent sur ce serveur',
                'journalctl absent sur ce serveur',
                'pas de fichier messages',
            ],
        )


if __name__ == '__main__':
    unittest.main()
