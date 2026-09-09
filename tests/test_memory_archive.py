#!/usr/bin/env python3
"""Oubli : archive froide vieux épisodes orphelins, référencés gardés."""

from __future__ import annotations

import gzip
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.memory.archive import archive_episodes  # noqa: E402
from serge.memory.lessons import add_lesson  # noqa: E402

NOW = '2026-09-09T19:00:00+00:00'
OLD = '2026-01-01T00:00:00+00:00'


class ArchiveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()
        self.tmp = tempfile.TemporaryDirectory()
        self.archive = Path(self.tmp.name) / 'archive'

    def tearDown(self) -> None:
        self.conn.close()
        self.tmp.cleanup()

    def _old_event(self) -> int:
        self.conn.execute(
            'INSERT INTO events(ts, actor, type) VALUES(?,?,?)',
            (OLD, 't', 'transition.x'),
        )
        row = self.conn.execute('SELECT last_insert_rowid()').fetchone()
        return int(row[0])

    def test_archive_orphelins_garde_references(self) -> None:
        orphan = self._old_event()
        kept = self._old_event()
        add_lesson(self.conn, 'X.', sources=[str(kept)])
        self.conn.execute(
            'INSERT INTO events(ts, actor, type) VALUES(?,?,?)',
            (NOW, 't', 'recent'),
        )
        result = archive_episodes(self.conn, self.archive, 30, NOW)
        self.assertEqual(result['count'], 1)
        self.assertTrue(Path(result['path']).is_file())
        raw = gzip.decompress(Path(result['path']).read_bytes()).decode()
        ids = [json.loads(line)['id'] for line in raw.strip().splitlines()]
        self.assertEqual(ids, [orphan])
        left = [row[0] for row in self.conn.execute('SELECT id FROM events')]
        self.assertIn(kept, left)
        self.assertNotIn(orphan, left)
        manifest = self.conn.execute(
            'SELECT count, sha256 FROM episode_archives'
        ).fetchone()
        self.assertEqual(manifest[0], 1)
        self.assertEqual(manifest[1], result['sha256'])

    def test_rien_a_faire(self) -> None:
        append_event(self.conn, actor='t', type='recent')
        result = archive_episodes(self.conn, self.archive, 30, NOW)
        self.assertEqual(result['count'], 0)
        self.assertEqual(result['path'], '')


if __name__ == '__main__':
    unittest.main()
