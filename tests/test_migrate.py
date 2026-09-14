#!/usr/bin/env python3
"""Migrations canon : vide → tête, déjà à jour, refus (trou / code trop vieux)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.migrate import (  # noqa: E402
    MigrateError,
    apply_pending,
    read_version,
)
from serge.db.schema import SCHEMA_VERSION, TABLES, init_schema  # noqa: E402


class MigrateTests(unittest.TestCase):
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
                migrations=((9, _noop), (11, _noop)),
                head=11,
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
            "SELECT id FROM pipeline_steps WHERE id='pre_prospection'"
        ).fetchone()
        self.assertIsNotNone(row)


if __name__ == '__main__':
    unittest.main()
