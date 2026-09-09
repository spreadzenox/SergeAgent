#!/usr/bin/env python3
"""Transport email gog : send/search/get mockés (pas de réseau)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.email_gog import (  # noqa: E402
    MailError,
    get_message,
    search_emails,
    send_email,
)


def _completed(payload: dict, code: int = 0, err: str = ''):
    return subprocess.CompletedProcess(['gog'], code, json.dumps(payload), err)


class EmailGogTests(unittest.TestCase):
    def test_send_ok(self) -> None:
        with mock.patch(
            'subprocess.run',
            return_value=_completed({'id': 'm1', 'threadId': 't1'}),
        ) as mocked:
            result = send_email('a@x.io', 'Sujet', 'Corps')
        self.assertEqual(
            (result['message_id'], result['thread_id']), ('m1', 't1')
        )
        args = mocked.call_args[0][0]
        self.assertIn('send', args)
        self.assertIn('--no-input', args)

    def test_send_invalide(self) -> None:
        with self.assertRaises(MailError):
            send_email('', 'S', 'B')

    def test_send_auth(self) -> None:
        with mock.patch(
            'subprocess.run',
            return_value=_completed({}, 1, 'auth permission denied'),
        ):
            with self.assertRaisesRegex(MailError, '^AUTH'):
                send_email('a@x.io', 'S', 'B')

    def test_binaire_manquant(self) -> None:
        with mock.patch('subprocess.run', side_effect=FileNotFoundError('x')):
            with self.assertRaisesRegex(MailError, '^BIN'):
                send_email('a@x.io', 'S', 'B')

    def test_search_et_get(self) -> None:
        with mock.patch(
            'subprocess.run',
            return_value=_completed({'messages': [{'id': 'm1'}]}),
        ):
            found = search_emails('newer_than:1d')
        self.assertEqual(found, [{'id': 'm1'}])
        with mock.patch(
            'subprocess.run',
            return_value=_completed({'id': 'm1', 'snippet': 'hi'}),
        ):
            message = get_message('m1')
        self.assertEqual(message['snippet'], 'hi')


if __name__ == '__main__':
    unittest.main()
