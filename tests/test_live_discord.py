#!/usr/bin/env python3
"""Smoke live Discord (live-prudent) : verify + send/edit/delete.

Skippé hors SERGE_ENV=test + SERGE_TEST_DISCORD_BOT_TOKEN +
SERGE_TEST_DISCORD_CHANNEL_ID. Cap 6 appels. Rien ne persiste
(message supprimé). Canal allowlist uniquement.
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.rest import (  # noqa: E402
    delete_message,
    edit_message,
    get_channel,
    send_message,
    verify_token,
)
from serge.testkit import SessionCap, require_live  # noqa: E402


class LiveDiscordTests(unittest.TestCase):
    def test_smoke_canal_allowlist(self) -> None:
        allowlist = require_live()
        token = os.environ.get('SERGE_TEST_DISCORD_BOT_TOKEN', '').strip()
        if not token:
            self.skipTest('SERGE_TEST_DISCORD_BOT_TOKEN requise')
        channel_id = str(allowlist.get('discord_channel_id') or '')
        if not channel_id:
            self.skipTest('SERGE_TEST_DISCORD_CHANNEL_ID requise')
        cap = SessionCap(6)
        cap.spend('verify')
        me = verify_token(token)
        self.assertTrue(me.get('id'))
        cap.spend('get_channel')
        channel = get_channel(token, channel_id)
        self.assertEqual(channel.get('name'), allowlist['discord_channel'])
        stamp = datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%SZ')
        cap.spend('send')
        sent = send_message(
            token,
            channel_id,
            {'content': f'🧪 smoke serge-tests ({stamp}, auto-supprimé)'},
        )
        self.assertTrue(sent.get('id'))
        cap.spend('edit')
        edit_message(
            token,
            channel_id,
            str(sent['id']),
            {'content': f'🧪 smoke serge-tests ({stamp}, édité)'},
        )
        cap.spend('delete')
        delete_message(token, channel_id, str(sent['id']))


if __name__ == '__main__':
    unittest.main()
