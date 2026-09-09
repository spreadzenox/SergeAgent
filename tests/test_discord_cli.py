#!/usr/bin/env python3
"""CLI Discord : config TOML + refus fail-closed."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.cli import BotError, load_discord_cfg, main  # noqa: E402

OWNER = '999988887777666555'


class DiscordCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env_backup = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._env_backup)

    def test_config(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            toml = Path(raw) / 'i.toml'
            toml.write_text(
                '[discord]\nguild_id = "1"\nforum_channel_id = "10"\n'
                'urgent_channel_id = "11"\ndigest_channel_id = "12"\n'
                f'owner_user_id = "{OWNER}"\n',
                encoding='utf-8',
            )
            cfg = load_discord_cfg(str(toml))
        self.assertEqual(cfg['owner_user_id'], OWNER)
        with self.assertRaises(BotError):
            load_discord_cfg('/tmp/serge-nope-instance.toml')
        os.environ.pop('SERGE_INSTANCE_FILE', None)
        with self.assertRaises(BotError):
            load_discord_cfg()

    def test_main_verify_sans_token(self) -> None:
        os.environ.pop('SERGE_INSTANCE_FILE', None)
        with tempfile.TemporaryDirectory() as raw:
            toml = Path(raw) / 'i.toml'
            toml.write_text('[discord]\n', encoding='utf-8')
            os.environ['SERGE_INSTANCE_FILE'] = str(toml)
            code = main(['verify'])
        self.assertEqual(code, 2)


if __name__ == '__main__':
    unittest.main()
