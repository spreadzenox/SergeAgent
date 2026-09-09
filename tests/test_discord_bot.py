#!/usr/bin/env python3
"""Bot Discord : interactions, réactions, miroir dû, délégation owner."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.discord.bot import Bot  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import create_ticket, publish  # noqa: E402

OWNER = '999988887777666555'
CFG = {
    'guild_id': '1',
    'forum_channel_id': '10',
    'urgent_channel_id': '11',
    'digest_channel_id': '12',
    'owner_user_id': OWNER,
}
POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'windows': {'quiet_hours': [[23, 0, 8, 0]]},
    'memory': {
        'consolidate_max_items': 10,
        'serge_md_max_lines': 100,
    },
}
NOW = '2026-09-09T19:00:00+00:00'
BOT_ID = '111122223333444455'


class DiscordBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def _bot(self) -> Bot:
        return Bot(self.conn, POLICY, dict(CFG), 'tok-fake-40')

    def test_interaction_applique_et_refresh(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'VETO_AMONT',
            'V',
            {'decision': 'x'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        bot = self._bot()
        interaction = {
            'id': '9001',
            'token': 'tok-ia-1',
            'type': 2,
            'member': {'user': {'id': OWNER}},
            'data': {'custom_id': f't:{ticket_id}:approuver'},
        }
        with (
            mock.patch('serge.discord.bot.interaction_callback') as acked,
            mock.patch('serge.discord.bot.mirror_ticket') as mirrored,
        ):
            bot.on_interaction(interaction)
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (ticket_id,)
        ).fetchone()[0]
        self.assertEqual(state, 'APPROVED')
        self.assertEqual(acked.call_args[0][2]['type'], 6)
        mirrored.assert_called_once()

    def test_interaction_non_owner(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'VETO_AMONT',
            'V',
            {'decision': 'x'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        bot = self._bot()
        interaction = {
            'id': '9002',
            'token': 'tok-ia-2',
            'type': 2,
            'member': {'user': {'id': '1111'}},
            'data': {'custom_id': f't:{ticket_id}:approuver'},
        }
        with mock.patch('serge.discord.bot.interaction_callback') as acked:
            bot.on_interaction(interaction)
        self.assertEqual(acked.call_args[0][2]['type'], 4)
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (ticket_id,)
        ).fetchone()[0]
        self.assertEqual(state, 'OPEN')

    def test_on_message_delegue_et_refresh(self) -> None:
        bot = self._bot()
        bot.bot_user_id = BOT_ID
        with (
            mock.patch(
                'serge.discord.owner_flow.handle_owner_message',
                return_value={'handled': True, 'ticket_id': 't_x'},
            ) as handled,
            mock.patch.object(bot, '_refresh') as refreshed,
        ):
            bot.on_message({'author': {'id': OWNER}, 'content': 'x'})
        handled.assert_called_once()
        refreshed.assert_called_once_with('t_x')

    def test_reaction_fil_digest(self) -> None:
        bot = self._bot()
        event = {
            'emoji': {'name': '🧵'},
            'channel_id': '12',
            'user_id': OWNER,
            'message_id': 'm9',
        }
        with mock.patch('serge.discord.bot.mirror_ticket'):
            bot.on_reaction(event)
        kinds = [
            row[0] for row in self.conn.execute('SELECT type FROM tickets')
        ]
        self.assertEqual(kinds, ['QNA'])
        bot.on_reaction({**event, 'emoji': {'name': '👍'}})
        count = self.conn.execute('SELECT COUNT(*) FROM tickets').fetchone()[0]
        self.assertEqual(count, 1)

    def test_mirror_due_h1_creation(self) -> None:
        ticket_id = create_ticket(
            self.conn, self.types, 'QNA', 'Q ?', {'question': 'q?'}, now=NOW
        )
        publish(self.conn, ticket_id)
        bot = self._bot()
        h1 = {
            'titre': 't',
            'ou': 'o',
            'enjeu': 'e',
            'attente': 'a',
            'fallback': '',
        }
        with (
            mock.patch(
                'serge.discord.bot.render_context_fr', return_value=h1
            ) as rendered,
            mock.patch(
                'serge.discord.bot.mirror_ticket',
                return_value={'forum': 'created'},
            ) as mirrored,
        ):
            count = bot.mirror_due()
        self.assertEqual(count, 1)
        rendered.assert_called_once()
        sent_h1 = mirrored.call_args[1]['h1']
        assert sent_h1 is not None
        self.assertEqual(
            sent_h1,
            {key: h1[key] for key in ('titre', 'ou', 'enjeu', 'attente')},
        )


if __name__ == '__main__':
    unittest.main()
