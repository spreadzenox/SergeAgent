#!/usr/bin/env python3
"""Canon v2: schema complet, init idempotente, events append-only."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db import (  # noqa: E402
    SCHEMA_VERSION,
    TABLES,
    append_event,
    init_schema,
    open_db,
    utcnow,
)


class CanonTests(unittest.TestCase):
    def test_all_tables_created(self) -> None:
        connection = sqlite3.connect(':memory:')
        try:
            init_schema(connection)
            names = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            for table in TABLES:
                self.assertIn(table, names)
            version = connection.execute(
                'SELECT version FROM schema_version'
            ).fetchone()[0]
            self.assertEqual(version, SCHEMA_VERSION)
        finally:
            connection.close()

    def test_init_is_idempotent(self) -> None:
        connection = sqlite3.connect(':memory:')
        try:
            init_schema(connection)
            init_schema(connection)
            count = connection.execute(
                'SELECT COUNT(*) FROM schema_version'
            ).fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            connection.close()

    def test_open_db_enforces_0600(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            db_path = Path(raw) / 'sub' / 'canon.db'
            connection = open_db(db_path)
            try:
                self.assertTrue(db_path.is_file())
            finally:
                connection.close()
            self.assertEqual(oct(db_path.stat().st_mode & 0o777), '0o600')

    def test_uniqueness_guards_idempotency(self) -> None:
        connection = sqlite3.connect(':memory:')
        try:
            init_schema(connection)
            connection.execute(
                'INSERT INTO work_items(id, kind, idempotency_key, created_at,'
                " updated_at) VALUES('w1','k','same',?,?)",
                (utcnow(), utcnow()),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    'INSERT INTO work_items(id, kind, idempotency_key,'
                    " created_at, updated_at) VALUES('w2','k','same',?,?)",
                    (utcnow(), utcnow()),
                )
            connection.execute(
                'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
                ' intent_id, created_at, updated_at)'
                " VALUES('t1','v','invoice',29.0,'intent-1',?,?)",
                (utcnow(), utcnow()),
            )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
                    ' intent_id, created_at, updated_at)'
                    " VALUES('t2','v','invoice',29.0,'intent-1',?,?)",
                    (utcnow(), utcnow()),
                )
        finally:
            connection.close()

    def test_append_event_roundtrip(self) -> None:
        connection = sqlite3.connect(':memory:')
        try:
            init_schema(connection)
            row_id = append_event(
                connection,
                actor='scheduler',
                type='transition.smoke_started',
                venture_id='v1',
                payload={'n': 50},
                links={'campaign': 'c1'},
            )
            connection.commit()
            row = connection.execute(
                'SELECT actor, type, venture_id FROM events WHERE id=?',
                (row_id,),
            ).fetchone()
            self.assertEqual(
                tuple(row), ('scheduler', 'transition.smoke_started', 'v1')
            )
        finally:
            connection.close()


if __name__ == '__main__':
    unittest.main()
