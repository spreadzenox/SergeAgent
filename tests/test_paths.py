#!/usr/bin/env python3
"""Chemins d'instance uniques : env, défauts, TOML."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import default_canon_path  # noqa: E402
from serge.paths import config_root, system_root  # noqa: E402


class PathsTests(unittest.TestCase):
    def test_system_root_defaut_et_env(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SERGE_SYSTEM_ROOT', None)
            self.assertEqual(system_root(), Path('/home/serge/serge-system'))
        with mock.patch.dict(os.environ, {'SERGE_SYSTEM_ROOT': '/tmp/x'}):
            self.assertEqual(system_root(), Path('/tmp/x'))
            self.assertEqual(
                default_canon_path(), Path('/tmp/x/state/serge.db')
            )

    def test_config_root_depuis_toml(self) -> None:
        with mock.patch.dict(
            os.environ, {'SERGE_INSTANCE_FILE': '/tmp/nope.toml'}
        ):
            self.assertEqual(
                config_root(), Path(os.path.expanduser('~/.config/serge'))
            )
        data = {
            'paths': {
                'home': '/home/owner',
                'config_root': '/home/owner/.config/serge',
            }
        }
        self.assertEqual(config_root(data), Path('/home/owner/.config/serge'))

    def test_config_root_defaut_home(self) -> None:
        self.assertEqual(
            config_root({'paths': {'home': '/home/o'}}),
            Path('/home/o/.config/serge'),
        )


if __name__ == '__main__':
    unittest.main()
