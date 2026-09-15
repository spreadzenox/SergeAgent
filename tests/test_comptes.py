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
    enregistrer_compte,
    ensure_account_columns,
    libelle_role,
    parse_targets,
)
from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402


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
            'SELECT role, profile_path, secret_ref, targets_json,'
            ' login, password'
            " FROM accounts_standing WHERE id='s1'"
        ).fetchone()
        self.assertEqual(row[0], 'ecoute')
        self.assertEqual(row[1], '')
        self.assertEqual(row[2], '')
        self.assertEqual(row[3], '[]')
        self.assertEqual(row[4], '')
        self.assertEqual(row[5], '')

    def test_enregistrer_puis_meme_lieu(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        premier = enregistrer_compte(
            conn,
            'reddit',
            'u/serge',
            'serge@atelier.io',
            'pw-un',
            role='ecoute',
            login_url='https://www.reddit.com/login',
        )
        self.assertTrue(premier.startswith('s_'))
        second = enregistrer_compte(
            conn,
            'reddit',
            'u/serge',
            'serge@atelier.io',
            'pw-deux',
            role='les_deux',
        )
        self.assertEqual(premier, second)
        row = conn.execute(
            'SELECT login, password, role, capital, login_url'
            ' FROM accounts_standing WHERE id=?',
            (premier,),
        ).fetchone()
        self.assertEqual(row[0], 'serge@atelier.io')
        self.assertEqual(row[1], 'pw-deux')
        self.assertEqual(row[2], 'les_deux')
        self.assertEqual(row[3], 1.0)
        self.assertEqual(row[4], 'https://www.reddit.com/login')
        autre = enregistrer_compte(
            conn, 'gmail', 'serge@atelier.io', 'serge@atelier.io', 'pw-mail'
        )
        self.assertNotEqual(premier, autre)

    def test_enregistrer_refuse_le_vide(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        with self.assertRaises(CompteError):
            enregistrer_compte(conn, 'reddit', 'u/x', '', 'pw')
        with self.assertRaises(CompteError):
            enregistrer_compte(conn, '', 'u/x', 'login', 'pw')
        with self.assertRaises(CompteError):
            enregistrer_compte(
                conn, 'reddit', 'u/x', 'login', 'pw', role='admin'
            )

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
