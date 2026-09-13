#!/usr/bin/env python3
"""Comptes web : colonnes crawl + migration depuis une vieille table."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.comptes import (  # noqa: E402
    COLONNES,
    CompteError,
    assert_role,
    dump_targets,
    ensure_account_columns,
    libelle_role,
    parse_targets,
)
from serge.db.schema import SCHEMA_VERSION, init_schema  # noqa: E402


class ComptesTests(unittest.TestCase):
    def test_init_pose_les_colonnes(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        have = {
            str(row[1])
            for row in conn.execute('PRAGMA table_info(accounts_standing)')
        }
        for name, _decl in COLONNES:
            self.assertIn(name, have)
        version = conn.execute(
            'SELECT version FROM schema_version'
        ).fetchone()[0]
        self.assertEqual(version, SCHEMA_VERSION)

    def test_alter_sur_vieille_table(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            'CREATE TABLE accounts_standing ('
            'id TEXT PRIMARY KEY, venue TEXT NOT NULL,'
            ' handle TEXT NOT NULL, capital REAL NOT NULL DEFAULT 1.0,'
            ' age_days INTEGER NOT NULL DEFAULT 0,'
            ' warnings INTEGER NOT NULL DEFAULT 0,'
            " status TEXT NOT NULL DEFAULT 'active',"
            " cooldown_until TEXT NOT NULL DEFAULT '',"
            ' updated_at TEXT NOT NULL)'
        )
        conn.execute(
            'INSERT INTO accounts_standing(id, venue, handle, updated_at)'
            " VALUES('s1','reddit','u/x','2026-09-13T12:00:00+00:00')"
        )
        ensure_account_columns(conn)
        row = conn.execute(
            'SELECT role, profile_path, secret_ref, targets_json'
            " FROM accounts_standing WHERE id='s1'"
        ).fetchone()
        self.assertEqual(row[0], 'ecoute')
        self.assertEqual(row[1], '')
        self.assertEqual(row[2], '')
        self.assertEqual(row[3], '[]')

    def test_role_et_cibles(self) -> None:
        self.assertEqual(libelle_role('ecoute'), 'Écouter')
        self.assertEqual(assert_role('les_deux'), 'les_deux')
        with self.assertRaises(CompteError):
            assert_role('admin')
        self.assertEqual(
            parse_targets(dump_targets([' https://r/', ''])),
            ['https://r/'],
        )
        self.assertEqual(parse_targets('pas-json'), [])
