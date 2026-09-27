#!/usr/bin/env python3
"""Empreintes du catalogue : calculées au boot, datées quand le code change."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.objet_sha import poser_shas, sha256_fichier  # noqa: E402


class EmpreintesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_boot_calcule_les_empreintes(self) -> None:
        code_sha, files_sha = self.conn.execute(
            "SELECT code_sha, files_sha FROM tools WHERE id='memory_search'"
        ).fetchone()
        self.assertEqual(
            code_sha, sha256_fichier(ROOT / 'serge/memory/search.py')
        )
        self.assertEqual(len(files_sha), 64)

    def test_code_modifie_change_empreinte_et_date(self) -> None:
        self.conn.execute(
            "UPDATE tools SET files_sha='ancien', updated_at='2020-01-01'"
            " WHERE id='memory_search'"
        )
        poser_shas(self.conn)
        files_sha, updated_at = self.conn.execute(
            "SELECT files_sha, updated_at FROM tools WHERE id='memory_search'"
        ).fetchone()
        self.assertNotEqual(files_sha, 'ancien')
        self.assertNotEqual(updated_at, '2020-01-01')

    def test_code_inchange_garde_la_date(self) -> None:
        self.conn.execute(
            "UPDATE tools SET updated_at='2020-01-01' WHERE id='memory_search'"
        )
        poser_shas(self.conn)
        updated_at = self.conn.execute(
            "SELECT updated_at FROM tools WHERE id='memory_search'"
        ).fetchone()[0]
        self.assertEqual(updated_at, '2020-01-01')


if __name__ == '__main__':
    unittest.main()
