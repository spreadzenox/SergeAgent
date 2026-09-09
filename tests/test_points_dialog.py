#!/usr/bin/env python3
"""Point P5 : tours temps réel, bornes, recentrage unique, filets."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.points.dialog import voice_turn  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'voice': {'max_turns': 12},
}
HISTORY = [{'role': 'user', 'text': 'Bonjour, c\u2019est combien ?'}]


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class DialogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_continue_ok(self) -> None:
        caller = _caller_for(
            json.dumps({'text': 'Bonjour ! Parlons-en.', 'action': 'continue'})
        )
        result = voice_turn(
            self.conn, POLICY, HISTORY, 'script', caller=caller
        )
        self.assertEqual(
            (result['action'], result['fallback']), ('continue', '')
        )

    def test_max_tours_sans_appel(self) -> None:
        caller = _caller_for(json.dumps({'text': 'x', 'action': 'continue'}))
        result = voice_turn(
            self.conn,
            POLICY,
            HISTORY,
            'script',
            turn_index=12,
            caller=caller,
        )
        self.assertEqual(result['action'], 'hangup')
        self.assertEqual(result['fallback'], 'max_turns')
        self.assertEqual(caller.n, 0)

    def test_recentrage_unique(self) -> None:
        caller = _caller_for(
            json.dumps({'text': 'Revenons à...', 'action': 'redirect'})
        )
        first = voice_turn(self.conn, POLICY, HISTORY, 'script', caller=caller)
        self.assertEqual(first['action'], 'redirect')
        caller2 = _caller_for(
            json.dumps({'text': 'Revenons à...', 'action': 'redirect'})
        )
        second = voice_turn(
            self.conn,
            POLICY,
            HISTORY,
            'script',
            redirected=True,
            caller=caller2,
        )
        self.assertEqual(second['action'], 'hangup')

    def test_filet_engagement(self) -> None:
        caller = _caller_for(
            json.dumps(
                {'text': 'Je vous garantis 10 clients.', 'action': 'continue'}
            )
        )
        result = voice_turn(
            self.conn,
            POLICY,
            HISTORY,
            'script',
            allowed_text='offre 99',
            caller=caller,
        )
        self.assertEqual(result['action'], 'hangup')
        self.assertEqual(result['fallback'], 'filet')

    def test_killed_secours(self) -> None:
        caller = _caller_for('no json')
        result = voice_turn(
            self.conn, POLICY, HISTORY, 'script', caller=caller
        )
        self.assertEqual(result['action'], 'hangup')
        self.assertIn('souci technique', result['text'])


if __name__ == '__main__':
    unittest.main()
