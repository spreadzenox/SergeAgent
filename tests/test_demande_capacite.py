#!/usr/bin/env python3
"""demande_capacite : ticket REQUESTED, refus si vide, pas de doublon."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.demande_capacite import CapaciteError, poser_demande  # noqa: E402
from serge.llm.outils_exec import HANDLERS, ContexteOutil  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402


class DemandeCapaciteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def test_pose_un_ticket_ouvert(self) -> None:
        out = poser_demande(
            self.conn,
            'écrire sur LinkedIn',
            point='qualify_prospect',
            contexte='pas de canal',
            types=self.types,
        )
        self.assertTrue(out['ok'])
        self.assertFalse(out['deja'])
        self.assertEqual(out['type'], 'REQUESTED')
        row = self.conn.execute(
            'SELECT type, title, state, payload_json FROM tickets WHERE id=?',
            (out['ticket_id'],),
        ).fetchone()
        self.assertEqual(row[0], 'REQUESTED')
        self.assertEqual(row[1], 'écrire sur LinkedIn')
        self.assertEqual(row[2], 'OPEN')
        payload = json.loads(row[3])
        self.assertEqual(payload['demande'], 'écrire sur LinkedIn')
        self.assertEqual(payload['point_llm'], 'qualify_prospect')
        self.assertEqual(payload['contexte'], 'pas de canal')

    def test_besoin_vide_refuse(self) -> None:
        with self.assertRaises(CapaciteError):
            poser_demande(self.conn, '   ', types=self.types)

    def test_meme_besoin_deja_ouvert(self) -> None:
        first = poser_demande(
            self.conn, 'navigateur', point='p1', types=self.types
        )
        again = poser_demande(
            self.conn, 'navigateur', point='p1', types=self.types
        )
        self.assertTrue(again['deja'])
        self.assertEqual(again['ticket_id'], first['ticket_id'])
        n = self.conn.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
        self.assertEqual(n, 1)

    def test_handler_invalide(self) -> None:
        ctx = ContexteOutil(self.conn, {}, {'context': {}}, 'voice_dialog')
        body = HANDLERS['demande_capacite'](ctx, {'besoin': ''})
        self.assertEqual(body['code'], 'invalide')


if __name__ == '__main__':
    unittest.main()
