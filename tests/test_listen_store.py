#!/usr/bin/env python3
"""Store écoute : dédup, batch non clusterisé, assignation."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.listen.store import (  # noqa: E402
    docs_in_cluster,
    save_docs,
    set_cluster,
    unclustered,
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

    def test_batch_et_assignation(self) -> None:
        save_docs(self.conn, [_doc('ld_a', 'A'), _doc('ld_b', 'B')], NOW)
        batch = unclustered(self.conn)
        self.assertEqual(len(batch), 2)
        self.assertEqual(set_cluster(self.conn, ['ld_a'], 'k1'), 1)
        self.assertEqual(
            [item['id'] for item in unclustered(self.conn)], ['ld_b']
        )
        self.assertEqual(
            [item['id'] for item in docs_in_cluster(self.conn, 'k1')],
            ['ld_a'],
        )
        self.assertEqual(set_cluster(self.conn, [], 'k1'), 0)


if __name__ == '__main__':
    unittest.main()
