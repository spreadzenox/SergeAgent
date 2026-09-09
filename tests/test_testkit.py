#!/usr/bin/env python3
"""Harnais live-prudent : cap dur, canon jetable, skip hors test."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.testkit import (  # noqa: E402
    SessionCap,
    SessionCapExceeded,
    require_live,
    temp_canon,
)


class TestkitTests(unittest.TestCase):
    def test_cap_bloque_au_max(self) -> None:
        cap = SessionCap(2)
        self.assertEqual(cap.spend('email'), 1)
        self.assertEqual(cap.spend('email'), 2)
        with self.assertRaises(SessionCapExceeded):
            cap.spend('email')
        with self.assertRaises(ValueError):
            SessionCap(0)

    def test_canon_jetable_isole(self) -> None:
        with temp_canon() as (connection, db_path):
            self.assertTrue(db_path.is_file())
            connection.execute(
                'INSERT INTO ventures(id, created_at, updated_at)'
                " VALUES('v','t','t')"
            )
            count = connection.execute(
                'SELECT COUNT(*) FROM ventures'
            ).fetchone()[0]
            self.assertEqual(count, 1)
            saved = str(db_path)
        self.assertFalse(Path(saved).exists())

    def test_require_live_skip_hors_test(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('SERGE_ENV', None)
            with self.assertRaises(unittest.SkipTest):
                require_live()


if __name__ == '__main__':
    unittest.main()
