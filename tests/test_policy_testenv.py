#!/usr/bin/env python3
"""Allowlist owner-only des tests live (B8). Depuis l'environnement."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.policy import PolicyError  # noqa: E402
from serge.testenv import load_test_allowlist  # noqa: E402


class AllowlistTests(unittest.TestCase):
    def test_allowlist_requires_test_env_and_valid_values(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SERGE_ENV', None)
            with self.assertRaises(PolicyError):
                load_test_allowlist()
        env = {
            'SERGE_ENV': 'test',
            'SERGE_TEST_EMAILS': 'a@example.com, b@example.com',
            'SERGE_TEST_SMS': '+33600000001',
            'SERGE_TEST_DISCORD_CHANNEL': 'serge-tests',
        }
        with mock.patch.dict(os.environ, env, clear=False):
            allow = load_test_allowlist()
        self.assertEqual(allow['emails'], ['a@example.com', 'b@example.com'])
        self.assertEqual(allow['sms'], ['+33600000001'])
        bad = dict(env, SERGE_TEST_SMS='not-a-number')
        with mock.patch.dict(os.environ, bad, clear=False):
            with self.assertRaises(PolicyError):
                load_test_allowlist()


if __name__ == '__main__':
    unittest.main()
