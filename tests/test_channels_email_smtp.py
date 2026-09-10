#!/usr/bin/env python3
"""Transport SMTP/IMAP mocké : send/search/get + erreurs typées."""

from __future__ import annotations

import imaplib
import os
import smtplib
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.mailbox_config import resolve_mailbox  # noqa: E402
from serge.channels.email_gog import MailError  # noqa: E402
from serge.channels.email_smtp import (  # noqa: E402
    get_message,
    search_emails,
    send_email,
)


def _config(**overrides):
    cfg = resolve_mailbox({'login': 'serge@example.net'})
    cfg['password'] = 'pw-fake-1'
    cfg.update(overrides)
    return cfg


class EmailSmtpTests(unittest.TestCase):
    def test_send_ok_starttls(self) -> None:
        with mock.patch('smtplib.SMTP') as smtp_cls:
            server = smtp_cls.return_value
            result = send_email('a@x.io', 'Sujet', 'Corps', config=_config())
        smtp_cls.assert_called_once()
        server.starttls.assert_called_once()
        server.login.assert_called_once_with('serge@example.net', 'pw-fake-1')
        server.send_message.assert_called_once()
        sent = server.send_message.call_args[0][0]
        self.assertEqual(
            (str(sent['To']), str(sent['Subject'])), ('a@x.io', 'Sujet')
        )
        self.assertTrue(result['message_id'].startswith('<'))
        self.assertEqual(result['thread_id'], '')

    def test_send_ssl_and_thread(self) -> None:
        cfg = _config(smtp_port=465, smtp_ssl=True)
        with (
            mock.patch('smtplib.SMTP_SSL') as ssl_cls,
            mock.patch('smtplib.SMTP') as plain_cls,
        ):
            send_email('a@x.io', 'S', 'C', thread_id='<p@x>', config=cfg)
        ssl_cls.assert_called_once()
        plain_cls.assert_not_called()
        server = ssl_cls.return_value
        sent = server.send_message.call_args[0][0]
        self.assertEqual(sent['In-Reply-To'], '<p@x>')

    def test_send_refusals(self) -> None:
        with self.assertRaises(MailError):
            send_email('', 'S', 'C', config=_config())
        with mock.patch('smtplib.SMTP') as smtp_cls:
            server = smtp_cls.return_value
            server.login.side_effect = smtplib.SMTPAuthenticationError(
                535, b'nope'
            )
            with self.assertRaises(MailError) as ctx:
                send_email('a@x.io', 'S', 'C', config=_config())
        self.assertIn('AUTH', str(ctx.exception))

    def test_search_newer_than_unseen(self) -> None:
        fetch = [
            (
                b'101 (UID 101 BODY[HEADER.FIELDS (MESSAGE-ID)] {20})',
                b'Message-ID: <a@x>\r\n',
            ),
            (
                b'102 (UID 102 BODY[HEADER.FIELDS (MESSAGE-ID)] {20})',
                b'Message-ID: <b@x>\r\n',
            ),
            b')',
        ]
        with mock.patch('imaplib.IMAP4_SSL') as cls:
            box = cls.return_value
            box.select.return_value = ('OK', [b'2'])
            box.uid.side_effect = [('OK', [b'101 102']), ('OK', fetch)]
            found = search_emails('newer_than:1d -in:sent', config=_config())
        self.assertEqual([entry['id'] for entry in found], ['<a@x>', '<b@x>'])
        args = list(box.uid.call_args_list[0][0])
        self.assertEqual(args[:4], ['search', 'CHARSET', 'US-ASCII', 'UNSEEN'])
        self.assertEqual(args[4], 'SINCE')
        self.assertRegex(args[5], r'^\d{2}-[A-Z][a-z]{2}-\d{4}$')

    def test_search_unknown_token_refused(self) -> None:
        with self.assertRaises(MailError) as ctx:
            search_emails('has:attachment', config=_config())
        self.assertIn('requete_non_supportee', str(ctx.exception))

    def test_search_auth_error(self) -> None:
        with mock.patch('imaplib.IMAP4_SSL') as cls:
            box = cls.return_value
            box.login.side_effect = imaplib.IMAP4.error('LOGIN failed nope')
            with self.assertRaises(MailError) as ctx:
                search_emails('', config=_config())
        self.assertIn('AUTH', str(ctx.exception))

    def test_get_message_parses_rfc822(self) -> None:
        raw = (
            b'From: Alice <alice@x.io>\r\nSubject: Hello\r\n'
            b'Message-ID: <m1@x>\r\nContent-Type: text/plain\r\n\r\n'
            b'Bonjour le monde'
        )
        with mock.patch('imaplib.IMAP4_SSL') as cls:
            box = cls.return_value
            box.select.return_value = ('OK', [b'1'])
            box.uid.return_value = ('OK', [(b'1 (RFC822 {90})', raw), b')'])
            message = get_message('uid:1', config=_config())
        headers = {
            item['name']: item['value']
            for item in message['payload']['headers']
        }
        self.assertEqual(headers['Subject'], 'Hello')
        self.assertIn('Bonjour', message['snippet'])

    def test_get_message_not_found(self) -> None:
        with mock.patch('imaplib.IMAP4_SSL') as cls:
            box = cls.return_value
            box.select.return_value = ('OK', [b'1'])
            box.uid.return_value = ('OK', [b''])
            with self.assertRaises(MailError) as ctx:
                get_message('<nope@x>', config=_config())
        self.assertIn('introuvable', str(ctx.exception))

    def test_send_without_instance_refuses(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(MailError) as ctx:
                send_email('a@x.io', 'S', 'C')
        self.assertIn('SERGE_INSTANCE_FILE', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
