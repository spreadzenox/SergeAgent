#!/usr/bin/env python3
"""Store écoute : dédup, batch non clusterisé, assignation."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.listen.store import (  # noqa: E402
    save_docs,
)

NOW = '2026-09-09T19:00:00+00:00'


def _doc(doc_id: str, title: str) -> dict[str, str]:
    return {
        'id': doc_id,
        'source': 'f',
        'title': title,
        'url': f'https://f.test/{doc_id}',
        'excerpt': title,
        'published': NOW,
    }


class ListenStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_dedup(self) -> None:
        docs = [_doc('ld_a', 'Prix trop cher'), _doc('ld_b', 'Autre')]
        self.assertEqual(save_docs(self.conn, docs, NOW), 2)
        self.assertEqual(save_docs(self.conn, docs, NOW), 0)


if __name__ == '__main__':
    unittest.main()
