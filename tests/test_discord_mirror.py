#!/usr/bin/env python3
"""Miroir Discord : forum/digest/urgent, idempotent, quiet hours."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.discord.mirror import (  # noqa: E402
    due_tickets,
    in_quiet_hours,
    mirror_ticket,
    read_ref,
)
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import add_item, create_ticket, publish  # noqa: E402

NOW = '2026-09-09T19:00:00+00:00'
NIGHT = '2026-09-09T23:30:00+00:00'
CFG = {
    'guild_id': '1',
    'forum_channel_id': '10',
    'urgent_channel_id': '11',
    'digest_channel_id': '12',
    'owner_user_id': '999988887777666555',
}
POLICY = {'windows': {'quiet_hours': [[23, 0, 8, 0]]}}


class DiscordMirrorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()
        self.types = load_ticket_types()

    def tearDown(self) -> None:
        self.conn.close()

    def _ticket_view(self, ticket_id: str) -> dict:
        from serge.tickets import get_ticket

        return get_ticket(self.conn, ticket_id)

    def test_quiet_hours(self) -> None:
        self.assertFalse(in_quiet_hours(POLICY, NOW))
        self.assertTrue(in_quiet_hours(POLICY, NIGHT))
        self.assertTrue(in_quiet_hours(POLICY, '2026-09-10T05:59:00+00:00'))
        self.assertFalse(in_quiet_hours(POLICY, '2026-09-10T06:00:00+00:00'))

    def test_forum_create_puis_fresh(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'VETO_AMONT',
            'Créer venture X',
            {'decision': 'go'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        with (
            mock.patch(
                'serge.discord.mirror.create_forum_post',
                return_value={'id': 'post1'},
            ) as created,
            mock.patch(
                'serge.discord.mirror.list_messages',
                return_value=[{'id': 'msg1'}],
            ),
        ):
            done = mirror_ticket(
                self.conn,
                'tok-fake-20',
                CFG,
                self._ticket_view(ticket_id),
                self.types['VETO_AMONT'],
                POLICY,
                now_iso=NOW,
            )
        self.assertEqual(done['forum'], 'created')
        self.assertFalse(done['urgent'])
        created.assert_called_once()
        ref = read_ref(
            self.conn.execute(
                'SELECT thread_ref FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        )
        self.assertEqual(ref['post_id'], 'post1')
        self.assertEqual(ref['message_id'], 'msg1')
        with mock.patch('serge.discord.mirror.edit_message') as edited:
            done = mirror_ticket(
                self.conn,
                'tok-fake-21',
                CFG,
                self._ticket_view(ticket_id),
                self.types['VETO_AMONT'],
                POLICY,
                now_iso=NOW,
            )
        self.assertEqual(done['forum'], 'fresh')
        edited.assert_not_called()

    def test_edit_sur_changement_etat(self) -> None:
        from serge.tickets import decide

        ticket_id = create_ticket(
            self.conn,
            self.types,
            'VETO_AMONT',
            'V',
            {'decision': 'x'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        self.conn.execute(
            'UPDATE tickets SET thread_ref=? WHERE id=?',
            (
                json.dumps(
                    {
                        'post_id': 'p',
                        'message_id': 'm',
                        'state': 'OPEN',
                        'items': 0,
                    }
                ),
                ticket_id,
            ),
        )
        decide(self.conn, ticket_id, 'APPROVED')
        with mock.patch(
            'serge.discord.mirror.edit_message', return_value={}
        ) as edited:
            done = mirror_ticket(
                self.conn,
                'tok-fake-22',
                CFG,
                self._ticket_view(ticket_id),
                self.types['VETO_AMONT'],
                POLICY,
                now_iso=NOW,
            )
        self.assertEqual(done['forum'], 'updated')
        edited.assert_called_once()
        ref = read_ref(
            self.conn.execute(
                'SELECT thread_ref FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        )
        self.assertEqual(ref['state'], 'APPROVED')

    def test_guichet_urgent_mention_jour(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'GUICHET',
            'CAPTCHA Malt',
            {'action_requise': 'captcha'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        with (
            mock.patch(
                'serge.discord.mirror.create_forum_post',
                return_value={'id': 'post2'},
            ),
            mock.patch('serge.discord.mirror.list_messages', return_value=[]),
            mock.patch(
                'serge.discord.mirror.send_message',
                return_value={'id': 'urg1'},
            ) as sent,
        ):
            done = mirror_ticket(
                self.conn,
                'tok-fake-23',
                CFG,
                self._ticket_view(ticket_id),
                self.types['GUICHET'],
                POLICY,
                now_iso=NOW,
            )
        self.assertTrue(done['urgent'])
        content = sent.call_args[0][2]['content']
        self.assertIn('<@999988887777666555>', content)

    def test_guichet_nuit_silencieux_sauf_ttl_court(self) -> None:
        long_id = create_ticket(
            self.conn,
            self.types,
            'GUICHET',
            'KYC',
            {'action_requise': 'kyc'},
            now=NIGHT,
            ttl_minutes=30,
        )
        publish(self.conn, long_id)
        with (
            mock.patch(
                'serge.discord.mirror.create_forum_post',
                return_value={'id': 'post3'},
            ),
            mock.patch('serge.discord.mirror.list_messages', return_value=[]),
            mock.patch(
                'serge.discord.mirror.send_message',
                return_value={'id': 'urg2'},
            ) as sent,
        ):
            done = mirror_ticket(
                self.conn,
                'tok-fake-24',
                CFG,
                self._ticket_view(long_id),
                self.types['GUICHET'],
                POLICY,
                now_iso=NIGHT,
            )
        self.assertTrue(done['urgent'])
        content = sent.call_args[0][2]['content']
        self.assertNotIn('<@999988887777666555>', content)
        self.assertIn('(silencieux)', content)
        short_id = create_ticket(
            self.conn,
            self.types,
            'GUICHET',
            'CAPTCHA',
            {'action_requise': 'captcha'},
            now=NIGHT,
            ttl_minutes=10,
        )
        publish(self.conn, short_id)
        with (
            mock.patch(
                'serge.discord.mirror.create_forum_post',
                return_value={'id': 'post4'},
            ),
            mock.patch('serge.discord.mirror.list_messages', return_value=[]),
            mock.patch(
                'serge.discord.mirror.send_message',
                return_value={'id': 'urg3'},
            ) as sent,
        ):
            mirror_ticket(
                self.conn,
                'tok-fake-26',
                CFG,
                self._ticket_view(short_id),
                self.types['GUICHET'],
                POLICY,
                now_iso=NIGHT,
            )
        content = sent.call_args[0][2]['content']
        self.assertIn('<@999988887777666555>', content)

    def test_fyi_digest(self) -> None:
        ticket_id = create_ticket(
            self.conn,
            self.types,
            'FYI',
            'Résultats',
            {'contenu': 'U3=3'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        with mock.patch(
            'serge.discord.mirror.send_message', return_value={'id': 'd1'}
        ) as sent:
            done = mirror_ticket(
                self.conn,
                'tok-fake-25',
                CFG,
                self._ticket_view(ticket_id),
                self.types['FYI'],
                POLICY,
                now_iso=NOW,
            )
        self.assertTrue(done['digest'])
        self.assertEqual(sent.call_args[0][1], '12')
        self.assertEqual(done['forum'], 'fresh')

    def test_due_tickets(self) -> None:
        first = create_ticket(
            self.conn, self.types, 'QNA', 'Q1', {'question': 'a?'}, now=NOW
        )
        publish(self.conn, first)
        second = create_ticket(
            self.conn, self.types, 'QNA', 'Q2', {'question': 'b?'}, now=NOW
        )
        publish(self.conn, second)
        self.conn.execute(
            'UPDATE tickets SET thread_ref=? WHERE id=?',
            (
                json.dumps(
                    {
                        'post_id': 'p',
                        'message_id': 'm',
                        'state': 'OPEN',
                        'items': 0,
                    }
                ),
                second,
            ),
        )
        self.assertEqual(due_tickets(self.conn), [first])
        add_item(self.conn, second, 'option', 'A')
        self.assertEqual(due_tickets(self.conn), [first, second])


if __name__ == '__main__':
    unittest.main()
