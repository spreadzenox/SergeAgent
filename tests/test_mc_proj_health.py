#!/usr/bin/env python3
"""Projecteurs P8 Santé : tests unitaires et goldens."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402
from serge.mc.proj_health import (  # noqa: E402
    project_audit_trail,
    project_charte_metriques,
    project_journal_serveur,
    project_versions_drift,
)

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}


class ProjHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn

        conn.execute(
            'INSERT INTO tickets(id, type, title, state, created_at, updated_at)'
            " VALUES('req1', 'REQUESTED', 'Filtre', 'OPEN', ?, ?)",
            (NOW, NOW),
        )
        conn.execute(
            'INSERT INTO events(ts, actor, type, payload_json) VALUES(?, ?, ?, ?)',
            (NOW, 'owner', 'mc_act', '{"acte": "kill", "point": "qualify"}'),
        )
        conn.commit()

    def test_charte_metriques(self) -> None:
        data = project_charte_metriques(self.conn, POLICY, NOW)
        self.assertIn('loc_total', data)
        self.assertTrue(data['loc_total'] > 1000)
        self.assertIn('plus_gros_fichier', data)
        self.assertTrue(data['plus_gros_fichier']['lignes'] > 0)
        self.assertEqual(data['requested_pending'], 1)

    def test_audit_trail(self) -> None:
        data = project_audit_trail(self.conn, POLICY, NOW)
        self.assertEqual(len(data['actes']), 1)
        acte = data['actes'][0]
        self.assertEqual(acte['acteur'], 'owner')
        self.assertEqual(acte['acte'], 'kill')
        self.assertEqual(acte['details']['point'], 'qualify')

    def test_versions_drift(self) -> None:
        data = project_versions_drift(self.conn, POLICY, NOW)
        self.assertEqual(data['schema_version'], SCHEMA_VERSION)
        self.assertTrue(data['schema_ok'])
        self.assertIn('mc_version', data)

    def test_journaux_du_bot_et_des_files(self) -> None:
        """Le journal du bot Discord et des deux files, lu par journalctl :
        un clic qui échoue y laisse sa trace."""
        lus = []

        def journalctl(cmd, **_kwargs):
            lus.append(cmd[cmd.index('--unit') + 1])
            return mock.Mock(
                returncode=0, stdout='discord : clic reçu\n', stderr=''
            )

        with (
            mock.patch(
                'serge.mc.proj_voice.shutil.which', return_value='/bin/x'
            ),
            mock.patch(
                'serge.mc.proj_voice.subprocess.run', side_effect=journalctl
            ),
        ):
            blocs = project_journal_serveur(self.conn, POLICY, NOW)['blocs']
        self.assertEqual(
            lus,
            [
                'serge-discord-bot.service',
                'serge-queue@conversations.service',
                'serge-queue@works.service',
            ],
        )
        self.assertEqual(blocs[0]['titre'], 'Bot Discord')
        self.assertEqual(blocs[0]['lignes'], ['discord : clic reçu'])


if __name__ == '__main__':
    unittest.main()
