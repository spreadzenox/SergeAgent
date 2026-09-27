#!/usr/bin/env python3
"""Tool contact_upsert : une fiche par personne, une ligne par adresse."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db_readers import tool_ids_for_point  # noqa: E402
from serge.funnels.contacts import addresses  # noqa: E402
from serge.llm.outils_exec import (  # noqa: E402
    HANDLERS,
    SCHEMAS,
    ContexteOutil,
)


def _email(value: str) -> dict[str, str]:
    return {'channel': 'email', 'value': value}


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

    def _nb_contacts(self) -> int:
        return self.conn.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]

    def test_schema_et_handler_sont_exposes(self) -> None:
        schema = SCHEMAS['contact_upsert']['function']
        self.assertEqual(schema['name'], 'contact_upsert')
        self.assertEqual(
            schema['parameters']['required'],
            ['venture_id', 'display', 'addresses'],
        )
        self.assertIsNotNone(HANDLERS['contact_upsert'])
        self.assertIn(
            'contact_upsert',
            tool_ids_for_point(self.conn, 'discover_contacts'),
        )

    def test_creation_avec_un_email(self) -> None:
        result = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[_email('Ada@Example.test')],
        )
        self.assertTrue(result['ok'])
        self.assertTrue(result['created'])
        self.assertEqual(
            addresses(self.conn, result['contact_id']),
            [
                {
                    'channel': 'email',
                    'value': 'Ada@Example.test',
                    'active': True,
                }
            ],
        )
        state = self.conn.execute(
            'SELECT funnel_state FROM contacts'
        ).fetchone()
        self.assertEqual(state[0], 'NEW')

    def test_meme_email_ajoute_le_telephone_a_la_meme_fiche(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[_email('ada@example.test')],
        )
        second = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[
                _email('ADA@EXAMPLE.TEST'),
                {'channel': 'phone', 'value': '+33 1 23 45 67 89'},
            ],
        )
        self.assertEqual(first['contact_id'], second['contact_id'])
        self.assertFalse(second['created'])
        self.assertEqual(
            second['added'],
            [{'channel': 'phone', 'value': '+33 1 23 45 67 89'}],
        )
        self.assertEqual(self._nb_contacts(), 1)

    def test_meme_telephone_regroupe(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[{'channel': 'phone', 'value': '+33 6 12 34 56 78'}],
        )
        second = self._call(
            venture_id='v1',
            display='Ada M.',
            addresses=[
                {'channel': 'phone', 'value': '+33612345678'},
                _email('ada@example.test'),
            ],
        )
        self.assertEqual(first['contact_id'], second['contact_id'])
        self.assertEqual(self._nb_contacts(), 1)

    def test_deuxieme_email_ajoute_sans_ecraser(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[
                {'channel': 'phone', 'value': '+33612345678'},
                _email('a@x.io'),
            ],
        )
        self._call(
            venture_id='v1',
            display='Ada',
            addresses=[
                {'channel': 'phone', 'value': '+33612345678'},
                _email('b@x.io'),
            ],
        )
        emails = [
            a['value']
            for a in addresses(self.conn, first['contact_id'])
            if a['channel'] == 'email'
        ]
        self.assertEqual(emails, ['a@x.io', 'b@x.io'])

    def test_email_generique_ne_regroupe_pas(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[_email('contact@acme.fr')],
        )
        second = self._call(
            venture_id='v1',
            display='Bob',
            addresses=[_email('Contact@acme.fr')],
        )
        self.assertNotEqual(first['contact_id'], second['contact_id'])
        self.assertEqual(self._nb_contacts(), 2)

    def test_meme_pseudo_sur_deux_reseaux_ne_regroupe_pas(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[{'channel': 'linkedin', 'value': 'Ada-42'}],
        )
        second = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[{'channel': 'reddit', 'value': 'Ada-42'}],
        )
        self.assertNotEqual(first['contact_id'], second['contact_id'])
        self.assertEqual(self._nb_contacts(), 2)

    def test_meme_email_dans_un_autre_business_ne_regroupe_pas(self) -> None:
        self.conn.execute(
            "INSERT INTO ventures(id, created_at, updated_at) VALUES('v2','t','t')"
        )
        first = self._call(
            venture_id='v1', display='Ada', addresses=[_email('ada@x.io')]
        )
        second = self._call(
            venture_id='v2', display='Ada', addresses=[_email('ada@x.io')]
        )
        self.assertNotEqual(first['contact_id'], second['contact_id'])

    def test_conflit_entre_deux_fiches_est_refuse_sans_ecriture(self) -> None:
        first = self._call(
            venture_id='v1',
            display='Ada',
            addresses=[_email('ada@example.test')],
        )
        second = self._call(
            venture_id='v1',
            display='Bob',
            addresses=[_email('bob@example.test')],
        )
        result = self._call(
            venture_id='v1',
            display='Fusion',
            addresses=[
                _email('ada@example.test'),
                _email('bob@example.test'),
                {'channel': 'phone', 'value': '+33123456789'},
            ],
        )
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'duplicate')
        self.assertEqual(
            set(result['matched_contact_ids']),
            {first['contact_id'], second['contact_id']},
        )
        self.assertEqual(self._nb_contacts(), 2)
        phones = self.conn.execute(
            "SELECT COUNT(*) FROM contact_addresses WHERE channel='phone'"
        ).fetchone()[0]
        self.assertEqual(phones, 0)

    def test_adresses_obligatoires(self) -> None:
        result = self._call(venture_id='v1', display='Ada', addresses=[])
        self.assertFalse(result['ok'])
        self.assertEqual(result['code'], 'invalide')
        result = self._call(venture_id='v1', display='Ada', email='a@x.io')
        self.assertFalse(result['ok'])
        self.assertEqual(self._nb_contacts(), 0)


if __name__ == '__main__':
    unittest.main()
