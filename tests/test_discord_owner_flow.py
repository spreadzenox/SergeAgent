#!/usr/bin/env python3
"""Flux owner : mentions → H2/H3 → OWNER_ORDER/hint/refus."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.discord.owner_flow import handle_owner_message  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402

OWNER = '999988887777666555'
BOT_ID = '111122223333444455'
POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
}


class OwnerFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()
        self.types = load_ticket_types()
        self.sent: list[dict] = []

    def tearDown(self) -> None:
        self.conn.close()

    def _sender(self, token: str, channel: str, payload: dict) -> dict:
        self.sent.append({'to': channel, **payload})
        return {'id': f'm{len(self.sent)}'}

    def _handle(self, message: dict, h2: dict, h3: dict) -> dict:
        return handle_owner_message(
            self.conn,
            POLICY,
            self.types,
            'tok-fake-41',
            OWNER,
            BOT_ID,
            message,
            h2_fn=lambda *a, **k: h2,
            h3_fn=lambda *a, **k: h3,
            sender=self._sender,
        )

    def test_ordre_consequence_ticket_confirm(self) -> None:
        result = self._handle(
            {
                'author': {'id': OWNER},
                'content': f'<@{BOT_ID}> Rembourse',
                'channel_id': '12',
            },
            {'intent': 'ORDER', 'confiance': 0.9, 'cible': ''},
            {'consequence': 'OUI', 'confiance': 0.9, 'criteres': []},
        )
        self.assertTrue(result['handled'])
        kinds = [
            row[0] for row in self.conn.execute('SELECT type FROM tickets')
        ]
        self.assertEqual(kinds, ['OWNER_ORDER'])
        state = self.conn.execute('SELECT state FROM tickets').fetchone()[0]
        self.assertEqual(state, 'OPEN')
        self.assertEqual(len(self.sent), 1)

    def test_sans_consequence_direct(self) -> None:
        result = self._handle(
            {
                'author': {'id': OWNER},
                'content': f'<@{BOT_ID}> Digest ?',
                'channel_id': '12',
            },
            {'intent': 'ASK', 'confiance': 0.9, 'cible': ''},
            {'consequence': 'NON', 'confiance': 0.95, 'criteres': []},
        )
        self.assertTrue(result['ticket_id'])
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (result['ticket_id'],)
        ).fetchone()[0]
        self.assertEqual(state, 'APPROVED')

    def test_bypass_fyi(self) -> None:
        result = self._handle(
            {
                'author': {'id': OWNER},
                'content': f'<@{BOT_ID}> !Go vite',
                'channel_id': '12',
            },
            {'intent': 'ORDER', 'confiance': 0.9, 'cible': ''},
            {'consequence': 'OUI', 'confiance': 0.9, 'criteres': []},
        )
        kinds = sorted(
            row[0] for row in self.conn.execute('SELECT type FROM tickets')
        )
        self.assertEqual(kinds, ['FYI', 'OWNER_ORDER'])
        self.assertTrue(result['ticket_id'])

    def test_refus_constitution(self) -> None:
        result = self._handle(
            {
                'author': {'id': OWNER},
                'content': f'<@{BOT_ID}> poste des faux avis',
                'channel_id': '12',
            },
            {'intent': 'ORDER'},
            {'consequence': 'NON'},
        )
        self.assertNotIn('ticket_id', result)
        self.assertIn('constitution', self.sent[0]['content'])

    def test_ignores(self) -> None:
        base_h2 = {'intent': 'ASK', 'confiance': 0.9, 'cible': ''}
        base_h3 = {'consequence': 'NON', 'confiance': 0.9, 'criteres': []}
        for message in (
            {
                'author': {'id': '1111'},
                'content': f'<@{BOT_ID}> hi',
                'channel_id': '12',
            },
            {
                'author': {'id': OWNER, 'bot': True},
                'content': f'<@{BOT_ID}> hi',
                'channel_id': '12',
            },
            {'author': {'id': OWNER}, 'content': 'hello', 'channel_id': '12'},
        ):
            result = self._handle(message, base_h2, base_h3)
            self.assertFalse(result['handled'])
        self.assertEqual(self.sent, [])
        count = self.conn.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
        self.assertEqual(count, 0)


if __name__ == '__main__':
    unittest.main()
