#!/usr/bin/env python3
"""Tool LLM contact_upsert : creation, enrichissement et deduplication."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db_readers import tool_ids_for_point  # noqa: E402
from serge.llm.outils_exec import (  # noqa: E402
    HANDLERS,
    SCHEMAS,
    ContexteOutil,
)


class ContactUpsertToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v1','t','t')"
        )
        self.ctx = ContexteOutil(self.conn, {}, {}, 'discover_contacts')

    def _call(self, **args):
        return HANDLERS['contact_upsert'](self.ctx, args)

    def test_schema_et_handler_sont_exposes(self) -> None:
        schema = SCHEMAS['contact_upsert']['function']
        self.assertEqual(schema['name'], 'contact_upsert')
        self.assertEqual(
            schema['parameters']['required'], ['venture_id', 'display']
        )
        self.assertIn(
            'contact_reference_by_canal', schema['parameters']['properties']
        )
        self.assertIn('reference', schema['parameters']['properties'])
        self.assertIsNotNone(HANDLERS['contact_upsert'])
        self.assertIn(
            'contact_upsert',
            tool_ids_for_point(self.conn, 'discover_contacts'),
        )

    def test_creation_email(self) -> None:
        result = self._call(
            venture_id='v1',
            display='Ada',
            contact_reference_by_canal={
                'email': {'address': 'Ada@Example.test', 'active': True}
            },
        )
        self.assertTrue(result['ok'])
        self.assertTrue(result['created'])
        self.assertFalse(result['enriched'])
        self.assertEqual(result['channels'], ['email'])
        row = self.conn.execute(
            'SELECT contact_reference_by_canal, funnel_state FROM contacts'
        ).fetchone()
        self.assertEqual(
            json.loads(row['contact_reference_by_canal'])['email']['address'],
            'Ada@Example.test',
        )
        self.assertEqual(row['funnel_state'], 'NEW')

    def test_ajout_telephone_au_meme_contact(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            reference={'channel': 'email', 'address': 'ada@example.test'},
        )
        second = self._call(
            venture_id='v1',
            display='Ada',
            contact_reference_by_canal={
                'email': {'address': 'ADA@EXAMPLE.TEST'},
                'voice': {'phone': '+33123456789'},
            },
        )
        self.assertEqual(first['contact_id'], second['contact_id'])
        self.assertTrue(second['enriched'])
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 1
        )
        refs = json.loads(
            self.conn.execute(
                'SELECT contact_reference_by_canal FROM contacts WHERE id=?',
                (first['contact_id'],),
            ).fetchone()[0]
        )
        self.assertEqual(refs['voice']['phone'], '+33123456789')
        self.assertTrue(refs['voice']['active'])

    def test_doublon_detecte_sur_un_autre_canal_est_enrichi(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            contact_reference_by_canal={'linkedin': {'handle': 'Ada-42'}},
        )
        second = self._call(
            venture_id='v1',
            display='Ada',
            contact_reference_by_canal={'reddit': {'handle': 'Ada-42'}},
        )
        self.assertEqual(first['contact_id'], second['contact_id'])
        self.assertEqual(
            second['matched_reference'][0]['existing_channel'], 'linkedin'
        )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 1
        )
        refs = json.loads(
            self.conn.execute(
                'SELECT contact_reference_by_canal FROM contacts WHERE id=?',
                (first['contact_id'],),
            ).fetchone()[0]
        )
        self.assertEqual(refs['reddit']['handle'], 'Ada-42')

    def test_conflit_entre_deux_contacts_est_refuse_sans_ecriture(
        self,
    ) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            contact_reference_by_canal={
                'email': {'address': 'ada@example.test'}
            },
        )
        second = self._call(
            venture_id='v1',
            display='Bob',
            contact_reference_by_canal={
                'email': {'address': 'bob@example.test'}
            },
        )
        result = self._call(
            venture_id='v1',
            display='Fusion',
            contact_reference_by_canal={
                'email': {'address': 'ada@example.test'},
                'voice': {'phone': '+33123456789'},
                'linkedin': {'handle': 'bob@example.test'},
            },
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'duplicate')
        self.assertEqual(
            set(result['matched_contact_ids']),
            {first['contact_id'], second['contact_id']},
        )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 2
        )

    def test_anciennes_colonnes_refusees(self) -> None:
        result = self._call(
            venture_id='v1',
            display='Ada',
            email='ada@example.test',
        )
        self.assertEqual(
            result,
            {
                'ok': False,
                'code': 'invalide',
                'detail': 'les anciennes colonnes de contact sont interdites',
            },
        )
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0], 0
        )


if __name__ == '__main__':
    unittest.main()
