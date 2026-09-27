#!/usr/bin/env python3
"""Migrations canon : vide → tête, déjà à jour, refus (trou / code trop vieux)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.migrate import (  # noqa: E402
    MigrateError,
    apply_pending,
    read_version,
)
from serge.db.schema import SCHEMA_VERSION, TABLES  # noqa: E402
from serge.db.v018 import apply_v018  # noqa: E402
from serge.db.v020 import apply_v020  # noqa: E402


class MigrateTests(unittest.TestCase):
    def test_v20_ajoute_les_metadonnees_llm_avec_defaults_valides(
        self,
    ) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            'CREATE TABLE llm_points (id TEXT PRIMARY KEY,'
            " updated_at TEXT NOT NULL DEFAULT 'legacy')"
        )
        conn.execute("INSERT INTO llm_points(id) VALUES('legacy')")
        apply_v020(conn)
        columns = {
            row[1]: row[4]
            for row in conn.execute('PRAGMA table_info(llm_points)')
        }
        self.assertEqual(columns['prompt'], "''")
        self.assertEqual(columns['output_mode'], "'text'")
        self.assertEqual(columns['external_info'], '0')
        self.assertEqual(
            conn.execute(
                "SELECT updated_at FROM llm_points WHERE id='legacy'"
            ).fetchone()[0],
            '',
        )
        conn.execute("INSERT INTO llm_points(id) VALUES('p')")
        self.assertEqual(
            conn.execute(
                'SELECT prompt, output_mode, external_info FROM llm_points'
            ).fetchone(),
            ('', 'text', 0),
        )

    def test_v18_backfill_reconstruit_contacts(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        conn.execute(
            """CREATE TABLE contacts (
                id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
                display TEXT NOT NULL DEFAULT '',
                email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
                venue TEXT NOT NULL DEFAULT '', handle TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL DEFAULT '',
                regime TEXT NOT NULL DEFAULT 'OUTBOUND',
                funnel_state TEXT NOT NULL DEFAULT 'NEW',
                last_inbound_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
            """
        )
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, phone, venue,'
            ' handle, profile_url, regime, funnel_state, created_at, updated_at)'
            " VALUES('p1','v1','Ada','ada@x.io','+33612345678','linkedin',"
            "'ada','https://linkedin.test/ada','INBOUND','ENGAGED','t','t')"
        )
        apply_v018(conn)
        columns = {
            row[1] for row in conn.execute('PRAGMA table_info(contacts)')
        }
        self.assertNotIn('email', columns)
        self.assertNotIn('phone', columns)
        row = conn.execute(
            'SELECT contact_reference_by_canal, regime, funnel_state'
            ' FROM contacts WHERE id=?',
            ('p1',),
        ).fetchone()
        references = json.loads(row[0])
        self.assertEqual(references['email']['address'], 'ada@x.io')
        self.assertEqual(references['voice']['phone'], '+33612345678')
        self.assertEqual(references['linkedin']['handle'], 'ada')
        self.assertEqual(row[1:], ('INBOUND', 'ENGAGED'))

    def test_vide_atteint_la_tete(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        reached = apply_pending(conn)
        self.assertEqual(reached, SCHEMA_VERSION)
        self.assertEqual(read_version(conn), SCHEMA_VERSION)
        names = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for table in TABLES:
            self.assertIn(table, names)

    def test_deja_a_jour_ne_restamp_pas(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)
        before = conn.execute(
            'SELECT version, applied_at FROM schema_version'
        ).fetchone()
        apply_pending(conn)
        after = conn.execute(
            'SELECT version, applied_at FROM schema_version'
        ).fetchone()
        self.assertEqual(before[0], after[0])
        self.assertEqual(before[1], after[1])

    def test_code_plus_vieux_que_la_db_refuse(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)
        conn.execute('DELETE FROM schema_version')
        conn.execute(
            'INSERT INTO schema_version(version, applied_at)'
            " VALUES(?, datetime('now'))",
            (SCHEMA_VERSION + 5,),
        )
        with self.assertRaises(MigrateError) as ctx:
            apply_pending(conn)
        self.assertIn('plus récent', str(ctx.exception))

    def test_trou_apres_le_socle_refuse(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn)

        def _noop(_conn: sqlite3.Connection) -> None:
            return None

        with self.assertRaises(MigrateError) as ctx:
            apply_pending(
                conn,
                migrations=(
                    (SCHEMA_VERSION, _noop),
                    (SCHEMA_VERSION + 2, _noop),
                ),
                head=SCHEMA_VERSION + 2,
            )
        self.assertIn('trou', str(ctx.exception))

    def test_v7_vers_v8_remappe_les_etapes(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        from serge.db.migrate import stamp
        from serge.db.schema import apply_v007

        apply_v007(conn)
        stamp(conn, 7)
        conn.execute(
            'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang)'
            " VALUES('ecoute', 0, '[]', 0), ('test', 1, '[]', 2)"
        )
        conn.execute(
            'INSERT INTO work_items(id, kind, idempotency_key, created_at,'
            " updated_at) VALUES('w1','listen.collect','k','t','t')"
        )
        self.assertEqual(apply_pending(conn), SCHEMA_VERSION)
        etape = conn.execute(
            "SELECT etape_id FROM work_items WHERE id='w1'"
        ).fetchone()[0]
        self.assertEqual(etape, 'pre_prospection')
        marche = conn.execute(
            "SELECT enabled FROM pipeline_steps WHERE id='pre_prospection'"
        ).fetchone()[0]
        self.assertEqual(marche, 0)

    def test_init_schema_seme_apres_migrate(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        row = conn.execute(
            'SELECT id, titre, files_sha, updated_at FROM pipeline_steps'
            " WHERE id='pre_prospection'"
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[1], 'Pré-prospection')
        self.assertTrue(row[2])
        self.assertTrue(row[3])
        lien = conn.execute(
            "SELECT de, vers, debit FROM etape_liens WHERE id='lourde-caisse'"
        ).fetchone()
        self.assertEqual(
            tuple(lien), ('prospection_lourde', 'caisse', 'transactions')
        )


if __name__ == '__main__':
    unittest.main()
