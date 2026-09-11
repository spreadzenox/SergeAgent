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

from serge.db.schema import SCHEMA_VERSION, init_schema  # noqa: E402
from serge.mc.proj_health import (  # noqa: E402
    project_audit_trail,
    project_charte_metriques,
    project_units_systemd,
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

    def test_units_systemd(self) -> None:
        with mock.patch('shutil.which', return_value=None):
            data = project_units_systemd(self.conn, POLICY, NOW)
            self.assertEqual(len(data['units']), 4)
            self.assertEqual(data['units'][0]['status'], 'inconnu')


if __name__ == '__main__':
    unittest.main()
