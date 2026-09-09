#!/usr/bin/env python3
"""Couche 5 : index FTS, filtres, budget, logs, redaction."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.memory.search import (  # noqa: E402
    index_document,
    memory_search,
    rebuild_index,
    redact_text,
    searches_spent,
)


class SearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_index_et_recherche(self) -> None:
        index_document(
            self.conn,
            'lesson',
            'l1',
            'Relancer les artisans par email J+3.',
            venture='v1',
            tags=['email'],
        )
        index_document(
            self.conn,
            'lesson',
            'l2',
            'Ne jamais appeler le dimanche.',
            venture='v1',
        )
        result = memory_search(self.conn, 'artisans email', point='p1')
        self.assertEqual(len(result['results']), 1)
        self.assertEqual(result['results'][0]['id'], 'l1')
        self.assertTrue(result['logged'])
        types = [
            row[0] for row in self.conn.execute('SELECT type FROM events')
        ]
        self.assertEqual(types, ['memory.search'])

    def test_filtres(self) -> None:
        index_document(
            self.conn, 'lesson', 'l1', 'Email artisans.', venture='v1'
        )
        index_document(
            self.conn,
            'ticket',
            't1',
            'Email ticket question.',
            venture='v2',
        )
        only_tickets = memory_search(
            self.conn, 'email', point='p', types=['ticket']
        )
        self.assertEqual(
            [item['id'] for item in only_tickets['results']], ['t1']
        )
        strict = memory_search(
            self.conn,
            'email',
            point='p',
            venture='v1',
            forbidden=['autres_ventures'],
        )
        self.assertEqual([item['id'] for item in strict['results']], ['l1'])

    def test_budget_tronque(self) -> None:
        index_document(self.conn, 'lesson', 'l1', 'Mot ' * 500, venture='')
        result = memory_search(self.conn, 'mot', point='p', budget_tokens=20)
        excerpt = result['results'][0]['extrait']
        self.assertIn('affine ta requête', excerpt)
        self.assertLessEqual(result['tokens_used'], 25)

    def test_redaction(self) -> None:
        self.assertEqual(
            redact_text('Écris à Ada.Lovelace@x.io vite'),
            'Écris à A…@x.io vite',
        )
        self.assertEqual(redact_text('Appelle +33612345678'), 'Appelle +…')
        index_document(
            self.conn, 'lesson', 'l1', 'Contact ada@x.io pour suivi.'
        )
        result = memory_search(self.conn, 'suivi', point='p')
        self.assertNotIn('ada@x.io', result['results'][0]['extrait'])

    def test_spent_et_rebuild(self) -> None:
        self.conn.execute(
            'INSERT INTO lessons(id, statement, created_at, updated_at)'
            " VALUES('l1','Email J+3.','t','t')"
        )
        count = rebuild_index(self.conn)
        self.assertGreaterEqual(count, 1)
        memory_search(self.conn, 'email', point='juge')
        memory_search(self.conn, 'email', point='juge')
        self.assertEqual(
            searches_spent(self.conn, 'juge', '2020-01-01T00:00:00+00:00'), 2
        )
        self.assertEqual(
            searches_spent(self.conn, 'autre', '2020-01-01T00:00:00+00:00'), 0
        )
        with self.assertRaises(ValueError):
            index_document(self.conn, 'nope', 'x', 'y')


if __name__ == '__main__':
    unittest.main()
