#!/usr/bin/env python3
"""Couche 4 : versioning résumés, rollback, SERGE.md."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.memory.summaries import (  # noqa: E402
    get_summary,
    put_summary,
    rollback_summary,
    serge_md_text,
)


class SummariesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_versionne_et_previous(self) -> None:
        first = put_summary(self.conn, 'thread', 'v1', 't1')
        self.assertEqual(first['version'], 1)
        second = put_summary(self.conn, 'thread', 'v2', 't1')
        self.assertEqual(second['version'], 2)
        found = get_summary(self.conn, 'thread', 't1')
        assert found is not None
        self.assertEqual((found['content'], found['previous']), ('v2', 'v1'))

    def test_rollback(self) -> None:
        put_summary(self.conn, 'serge_md', 'v1')
        put_summary(self.conn, 'serge_md', 'v2')
        self.assertTrue(rollback_summary(self.conn, 'serge_md'))
        found = get_summary(self.conn, 'serge_md')
        assert found is not None
        self.assertEqual(found['content'], 'v1')
        self.assertEqual(found['version'], 3)
        self.assertFalse(rollback_summary(self.conn, 'nope'))

    def test_serge_md_absent(self) -> None:
        self.assertEqual(serge_md_text(self.conn), '')
        self.assertIsNone(get_summary(self.conn, 'thread', 'zz'))


if __name__ == '__main__':
    unittest.main()
