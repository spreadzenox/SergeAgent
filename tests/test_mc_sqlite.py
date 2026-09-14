#!/usr/bin/env python3
"""Fenêtre SQLite : miroir des tables réellement présentes."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import TABLES  # noqa: E402
from serge.mc.proj_sqlite import project_sqlite, project_table  # noqa: E402


class SqliteMiroirTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_voit_les_tables_du_schema(self) -> None:
        data = project_sqlite(self.conn)
        ids = [ligne['id'] for ligne in data['tableau']['lignes']]
        self.assertIn('pipeline_steps', ids)
        for nom in TABLES:
            self.assertIn(nom, ids)

    def test_voit_une_table_ajoutee(self) -> None:
        self.conn.execute('CREATE TABLE extra_live(x INTEGER)')
        data = project_sqlite(self.conn)
        ids = [ligne['id'] for ligne in data['tableau']['lignes']]
        self.assertIn('extra_live', ids)
        fiche = project_table(self.conn, 'extra_live')
        assert fiche is not None
        self.assertEqual(fiche['id'], 'extra_live')
        self.assertEqual(fiche['champs'][3]['v'], '1')


if __name__ == '__main__':
    unittest.main()
