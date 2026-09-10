#!/usr/bin/env python3
"""Mailbox presets + résolution : défauts, custom, refus."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from kit.mailbox_config import (  # noqa: E402
    MailboxError,
    resolve_mailbox,
)


class MailboxConfigTests(unittest.TestCase):
    def test_infomaniak_default_resolves(self) -> None:
        cfg = resolve_mailbox({'login': 'serge@example.net'})
        self.assertEqual(cfg['smtp_host'], 'mail.infomaniak.com')
        self.assertEqual((cfg['smtp_port'], cfg['smtp_ssl']), (587, False))
        self.assertEqual((cfg['imap_port'], cfg['imap_ssl']), (993, True))
        self.assertEqual(cfg['login'], 'serge@example.net')

    def test_known_presets_hosts(self) -> None:
        for preset, smtp, imap in (
            ('gmail', 'smtp.gmail.com', 'imap.gmail.com'),
            ('fastmail', 'smtp.fastmail.com', 'imap.fastmail.com'),
        ):
            cfg = resolve_mailbox({'preset': preset, 'login': 'a@b.c'})
            self.assertEqual(
                (cfg['smtp_host'], cfg['imap_host']), (smtp, imap)
            )

    def test_custom_overrides_and_ssl_flags(self) -> None:
        cfg = resolve_mailbox(
            {
                'preset': 'custom',
                'login': 'a@b.c',
                'smtp_host': 'smtp.example.net',
                'smtp_port': 465,
                'imap_host': 'imap.example.net',
                'imap_port': 143,
            }
        )
        self.assertEqual((cfg['smtp_ssl'], cfg['imap_ssl']), (True, False))

    def test_refusals(self) -> None:
        with self.assertRaises(MailboxError):
            resolve_mailbox({'preset': 'nope', 'login': 'a@b.c'})
        with self.assertRaises(MailboxError):
            resolve_mailbox({'login': ''})
        with self.assertRaises(MailboxError):
            resolve_mailbox({'preset': 'custom', 'login': 'a@b.c'})
        with self.assertRaises(MailboxError):
            resolve_mailbox({'login': 'a@b.c', 'smtp_port': 'beaucoup'})
        with self.assertRaises(MailboxError):
            resolve_mailbox({'login': 'a@b.c', 'imap_port': 99999})


if __name__ == '__main__':
    unittest.main()
