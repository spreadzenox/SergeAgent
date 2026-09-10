#!/usr/bin/env python3
"""Routage email : SERGE_EMAIL_BACKEND=smtp -> SMTP/IMAP, sinon gog."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import serge.channels as channels  # noqa: E402


class ChannelsRoutingTests(unittest.TestCase):
    def test_default_routes_gog(self) -> None:
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch.object(
                channels.email_gog,
                'send_email',
                return_value={'message_id': 'g', 'thread_id': ''},
            ) as gog,
            mock.patch.object(channels.email_smtp, 'send_email') as smtp,
        ):
            result = channels.send_email('a@x.io', 'S', 'C')
        gog.assert_called_once()
        smtp.assert_not_called()
        self.assertEqual(result['message_id'], 'g')

    def test_smtp_env_routes_smtp(self) -> None:
        with (
            mock.patch.dict(os.environ, {'SERGE_EMAIL_BACKEND': 'smtp'}),
            mock.patch.object(channels.email_gog, 'send_email') as gog,
            mock.patch.object(
                channels.email_smtp,
                'send_email',
                return_value={'message_id': 's', 'thread_id': ''},
            ) as smtp,
        ):
            result = channels.send_email('a@x.io', 'S', 'C')
        smtp.assert_called_once()
        gog.assert_not_called()
        self.assertEqual(result['message_id'], 's')


if __name__ == '__main__':
    unittest.main()
