#!/usr/bin/env python3
"""Tools db_read catalogués et capsules mémoire."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.query_builder import (  # noqa: E402
    DbReadError,
    execute_db_read,
    openai_schema_for_tool,
)
from serge.db_readers import execute_memory_capsule  # noqa: E402


class DbToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.executemany(
            'INSERT INTO business_candidates'
            '(id, title, content, normalized_key, status, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?)',
            [
                ('b1', 'A', 'a', 'k1', 'CANDIDATE', 't', 't'),
                ('b2', 'B', 'b', 'k2', 'POC_SELECTED', 't', 't'),
            ],
        )

    def tearDown(self) -> None:
        self.conn.close()

    def test_tools_db_sont_individualises_et_sans_facade(self) -> None:
        rows = self.conn.execute(
            "SELECT id, kind FROM tools WHERE kind='db_read' ORDER BY id"
        ).fetchall()
        self.assertEqual(
            [tuple(row) for row in rows],
            [
                ('current_listen_cycle', 'db_read'),
                ('eligible_poc_candidates', 'db_read'),
                ('known_business_candidates', 'db_read'),
                ('listen_cycle_documents', 'db_read'),
            ],
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM tools WHERE id='db_read'"
            ).fetchone()
        )

    def test_schema_openai_vient_des_parametres_et_colonnes_catalogues(
        self,
    ) -> None:
        schema = openai_schema_for_tool(self.conn, 'listen_cycle_documents')
        parameters = schema['function']['parameters']
        self.assertEqual(parameters['required'], ['cycle_id'])
        self.assertIn('cycle_id', parameters['properties'])
        self.assertIn(
            'listen_cycle_docs.cycle_id',
            parameters['properties']['columns']['items']['enum'],
        )
        join_properties = parameters['properties']['joins']['items'][
            'properties'
        ]
        self.assertNotIn('join_id', join_properties)
        self.assertIn(
            'listen_cycle_docs', join_properties['left_table']['enum']
        )
        self.assertIn('doc_id', join_properties['left_column']['enum'])

    def test_filtres_fixes_et_parametres_sont_appliques(self) -> None:
        result = execute_db_read(self.conn, 'eligible_poc_candidates', {})
        self.assertEqual([row['id'] for row in result['data']], ['b1'])
        with self.assertRaises(DbReadError):
            execute_db_read(
                self.conn,
                'eligible_poc_candidates',
                {'status': "CANDIDATE' OR 1=1 --"},
            )

    def test_jointure_et_colonne_hors_catalogue_sont_refusees(self) -> None:
        with self.assertRaises(DbReadError):
            execute_db_read(
                self.conn,
                'listen_cycle_documents',
                {
                    'cycle_id': 'c1',
                    'joins': [{'join_id': 'pas-permis'}],
                },
            )
        with self.assertRaises(DbReadError):
            execute_db_read(
                self.conn,
                'known_business_candidates',
                {'columns': ['business_candidates.id;DROP TABLE tools']},
            )
        with self.assertRaises(DbReadError):
            execute_db_read(
                self.conn,
                'listen_cycle_documents',
                {
                    'joins': [
                        {
                            'left_table': 'listen_cycle_docs',
                            'left_column': 'cycle_id',
                            'right_table': 'not_allowed',
                            'right_column': 'id',
                        }
                    ]
                },
            )
        with self.assertRaises(DbReadError):
            execute_db_read(
                self.conn,
                'listen_cycle_documents',
                {
                    'joins': [
                        {
                            'left_table': 'listen_cycle_docs',
                            'left_column': 'secret',
                            'right_table': 'listen_docs',
                            'right_column': 'id',
                        }
                    ]
                },
            )

    def test_tool_mult_tables_jointure_sans_catalogue_de_jointures(
        self,
    ) -> None:
        self.conn.execute(
            'INSERT INTO listen_docs(id, source, title, fetched_at) '
            "VALUES('d1', 'forum', 'Besoin', 't')"
        )
        self.conn.execute(
            "INSERT INTO listen_cycle_docs(cycle_id, doc_id) VALUES('c1', 'd1')"
        )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM tool_db_joins').fetchone()[
                0
            ],
            0,
        )
        result = execute_db_read(
            self.conn,
            'listen_cycle_documents',
            {
                'cycle_id': 'c1',
                'columns': ['listen_cycle_docs.cycle_id', 'listen_docs.title'],
                'joins': [
                    {
                        'left_table': 'listen_cycle_docs',
                        'left_column': 'doc_id',
                        'right_table': 'listen_docs',
                        'right_column': 'id',
                    }
                ],
            },
        )
        self.assertEqual(
            result['data'], [{'cycle_id': 'c1', 'title': 'Besoin'}]
        )

    def test_capsule_inclut_materiel_et_parametres_fixes(self) -> None:
        self.conn.execute(
            'INSERT INTO db_reader_fixed_params(capsule_id, param_name, value_text)'
            " VALUES('eligible_poc_candidates', 'limit', '1')"
        )
        result = execute_memory_capsule(
            self.conn, 'eligible_poc_candidates', {}
        )
        self.assertTrue(result['ok'])
        self.assertEqual(len(result['data']), 1)
        self.assertIn('description', result)
        self.assertIn('prompt_addition', result)

    def test_capsule_impose_une_jointure_fixe(self) -> None:
        self.conn.execute(
            'INSERT INTO listen_docs(id, source, title, fetched_at) '
            "VALUES('d1', 'forum', 'Besoin', 't')"
        )
        self.conn.execute(
            "INSERT INTO listen_cycle_docs(cycle_id, doc_id) VALUES('c1', 'd1')"
        )
        result = execute_memory_capsule(
            self.conn, 'listen_cycle_documents', {'cycle_id': 'c1'}
        )
        self.assertTrue(result['ok'])
        self.assertEqual(result['data'][0]['title'], 'Besoin')


if __name__ == '__main__':
    unittest.main()
