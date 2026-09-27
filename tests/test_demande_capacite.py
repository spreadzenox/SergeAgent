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

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.demande_capacite import CapaciteError, poser_demande  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
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
            point='classify_reply',
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
        self.assertEqual(payload['point_llm'], 'classify_reply')
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

    def test_toute_invocation_peut_demander_une_capacite(self) -> None:
        """Une invocation sans outil déclaré demande quand même à Julien.

        L'outil « Demander une nouvelle capacité » est donné partout : le
        faux modèle l'appelle deux fois (une demande vide, refusée, puis
        une vraie), puis rend sa réponse.
        """
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {'id': 'redacteur', 'type': 'llm', 'prompt': 'Écris.'}
                ],
            },
        )
        enqueue_task(self.conn, 'redacteur', {})
        set_heartbeat(self.conn, True)
        self.conn.commit()
        seen: list[list] = []

        def model(_key, name, messages, **kwargs):
            seen.append([t['function']['name'] for t in kwargs['tools']])
            answers = [m for m in messages if m.get('role') == 'tool']
            if not answers:
                calls = (
                    ToolCall('c1', 'demande_capacite', '{"need": " "}'),
                    ToolCall(
                        'c2',
                        'demande_capacite',
                        '{"need": "écrire sur LinkedIn"}',
                    ),
                )
                return ChatResult('', 5, 5, name, 1, calls)
            self.assertIn('echec', answers[0]['content'])
            return ChatResult('Fait.', 5, 5, name, 1)

        process_one(
            self.conn, 'works', now='2026-09-28T10:00:00+00:00', caller=model
        )
        self.assertEqual(seen[0], ['demande_capacite'])
        row = self.conn.execute(
            "SELECT title, payload_json FROM tickets WHERE type='REQUESTED'"
        ).fetchone()
        self.assertEqual(row[0], 'écrire sur LinkedIn')
        self.assertEqual(json.loads(row[1])['point_llm'], 'redacteur')


if __name__ == '__main__':
    unittest.main()
