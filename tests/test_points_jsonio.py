#!/usr/bin/env python3
"""IO JSON points : extraction tolérante, recalls bornés, fallback direct."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.points.jsonio import extract_json, run_json  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 2},
}
SPECLESS = 'classify_reply'


def _caller_for(*texts: str):
    calls: list[list[dict]] = []

    def _call(*args, **kwargs):
        calls.append(list(args[2]))
        index = min(len(calls) - 1, len(texts) - 1)
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


class JsonioTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_extract_json(self) -> None:
        self.assertEqual(extract_json('{"a": 1}'), {'a': 1})
        self.assertEqual(extract_json('Voici : {"a": 1} merci'), {'a': 1})
        self.assertIsNone(extract_json('pas de json'))
        self.assertIsNone(extract_json(''))
        self.assertIsNone(extract_json('[1, 2]'))

    def test_ok_premier_coup(self) -> None:
        caller = _caller_for('{"classe": "MEETING"}')
        data, result = run_json(
            self.conn,
            POLICY,
            SPECLESS,
            [{'role': 'user', 'content': 'x'}],
            lambda obj: obj.get('classe') == 'MEETING',
            caller=caller,
        )
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(data, {'classe': 'MEETING'})
        self.assertEqual(len(caller.calls), 1)

    def test_recall_repare(self) -> None:
        caller = _caller_for('blabla', '{"classe": "MEETING"}')
        data, result = run_json(
            self.conn,
            POLICY,
            SPECLESS,
            [{'role': 'user', 'content': 'x'}],
            lambda obj: 'classe' in obj,
            caller=caller,
        )
        assert result is not None
        self.assertTrue(result.ok)
        self.assertEqual(data, {'classe': 'MEETING'})
        self.assertEqual(len(caller.calls), 2)
        self.assertIn('JSON', caller.calls[1][-1]['content'])

    def test_epuise_recalls(self) -> None:
        caller = _caller_for('nope')
        data, result = run_json(
            self.conn,
            POLICY,
            SPECLESS,
            [{'role': 'user', 'content': 'x'}],
            lambda obj: True,
            caller=caller,
        )
        assert result is not None
        self.assertTrue(result.ok)
        self.assertIsNone(data)
        self.assertEqual(len(caller.calls), 3)

    def test_fallback_sans_recall(self) -> None:
        caller = _caller_for('{"classe": "X"}')
        data, result = run_json(
            self.conn,
            POLICY,
            'nope_zzz_point',
            [{'role': 'user', 'content': 'x'}],
            lambda obj: True,
            caller=caller,
        )
        assert result is not None
        self.assertFalse(result.ok)
        self.assertEqual(result.fallback, 'killed')
        self.assertIsNone(data)
        self.assertEqual(len(caller.calls), 0)


if __name__ == '__main__':
    unittest.main()
