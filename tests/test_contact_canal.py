#!/usr/bin/env python3
"""Traces par lieu : upsert, deux lieux restent deux lignes, refus."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402
from serge.funnels.contact_canal import (  # noqa: E402
    ContactCanalError,
    upsert_trace,
)
from serge.mc.proj_objet import project_objet  # noqa: E402


class ContactCanalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, created_at, updated_at)'
            " VALUES('v1','t','t')"
        )

    def test_schema(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 12)

    def test_meme_lieu_enrichit(self) -> None:
        premier = upsert_trace(
            self.conn, 'v1', 'linkedin', 'ada', display='Ada'
        )
        second = upsert_trace(
            self.conn,
            'v1',
            'linkedin',
            'ada',
            email='ada@x.io',
            profile_url='https://linkedin.com/in/ada',
        )
        self.assertEqual(premier, second)
        row = self.conn.execute(
            'SELECT email, display, profile_url, venue FROM contacts'
            ' WHERE id=?',
            (premier,),
        ).fetchone()
        self.assertEqual(row['email'], 'ada@x.io')
        self.assertEqual(row['display'], 'Ada')
        self.assertIn('linkedin.com', row['profile_url'])
        self.assertEqual(row['venue'], 'linkedin')

    def test_deux_lieux_deux_lignes(self) -> None:
        linkedin = upsert_trace(
            self.conn, 'v1', 'linkedin', 'ada', email='ada@x.io'
        )
        reddit = upsert_trace(self.conn, 'v1', 'reddit', 'u/ada')
        self.assertNotEqual(linkedin, reddit)
        n = self.conn.execute(
            'SELECT COUNT(*) FROM contacts WHERE venture_id=?', ('v1',)
        ).fetchone()[0]
        self.assertEqual(n, 2)

    def test_vide_refuse(self) -> None:
        with self.assertRaises(ContactCanalError):
            upsert_trace(self.conn, 'v1', '', 'ada')
        with self.assertRaises(ContactCanalError):
            upsert_trace(self.conn, 'v1', 'reddit', '  ')

    def test_fiche_montre_le_lieu(self) -> None:
        ident = upsert_trace(self.conn, 'v1', 'reddit', 'u/ada')
        fiche = project_objet(self.conn, 'prospect', ident)
        assert fiche is not None
        vals = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(vals['Lieu'], 'reddit')
        self.assertEqual(vals['Sur ce lieu'], 'u/ada')


if __name__ == '__main__':
    unittest.main()
