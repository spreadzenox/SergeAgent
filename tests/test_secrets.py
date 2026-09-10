#!/usr/bin/env python3
"""Lecteur secrets unique : brut, dotenv, base64, absent."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from serge.secrets import read_secret_file  # noqa: E402


class SecretsTests(unittest.TestCase):
    def _write(self, tmp: Path, name: str, body: str) -> Path:
        path = tmp / name
        path.write_text(body, encoding='utf-8')
        return path

    def test_formats(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            self.assertEqual(
                read_secret_file(self._write(tmp, 'a', 'tok-brut-1\n')),
                'tok-brut-1',
            )
            self.assertEqual(
                read_secret_file(
                    self._write(tmp, 'b', 'XAI_API_KEY=xai-fake-1\n')
                ),
                'xai-fake-1',
            )
            self.assertEqual(
                read_secret_file(self._write(tmp, 'c', 'k="quoted-fake-2"\n')),
                'quoted-fake-2',
            )
            self.assertEqual(read_secret_file(tmp / 'nope'), '')
            self.assertEqual(
                read_secret_file(self._write(tmp, 'd', '\n  \n')), ''
            )

    def test_base64_padding_non_deshabille(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            tmp = Path(raw)
            blob = 'V2VsY29tZQ924vMDEyPGh+'
            self.assertEqual(
                read_secret_file(self._write(tmp, 'e', blob + '==\n')),
                blob + '==',
            )
            self.assertEqual(
                read_secret_file(self._write(tmp, 'f', 'XKEY=\n')), ''
            )


if __name__ == '__main__':
    unittest.main()
