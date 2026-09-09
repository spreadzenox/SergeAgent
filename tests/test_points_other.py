#!/usr/bin/env python3
"""Point O4 : juge OTHER batch, reclassements + proposition."""

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
from serge.points.other import review_other_batch  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {'other_batch_max_items': 2},
}

ITEMS = [
    {'id': 'e1', 'channel': 'email', 'native_type': 'X', 'excerpt': 'bla'},
    {'id': 'e2', 'channel': 'email', 'native_type': 'Y', 'excerpt': 'bli'},
    {'id': 'e3', 'channel': 'email', 'native_type': 'Z', 'excerpt': 'blo'},
]


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class OtherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_reclasse_et_propose(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'reclass': [
                        {'id': 'e1', 'signal': 'REPLIED', 'confiance': 0.8},
                        {'id': 'e2', 'signal': 'OTHER', 'confiance': 0.5},
                    ],
                    'proposition': {
                        'nom': 'BOUNCE_MOU',
                        'definition': 'x',
                        'exemples': ['e2'],
                    },
                }
            )
        )
        result = review_other_batch(
            self.conn, POLICY, ITEMS[:2], caller=caller
        )
        self.assertEqual(len(result['reclass']), 2)
        self.assertEqual(result['proposition']['nom'], 'BOUNCE_MOU')
        self.assertFalse(result['truncated'])
        self.assertEqual(result['fallback'], '')

    def test_cap_tronque(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'reclass': [
                        {'id': 'e1', 'signal': 'SEEN', 'confiance': 0.7}
                    ],
                    'proposition': None,
                }
            )
        )
        result = review_other_batch(self.conn, POLICY, ITEMS, caller=caller)
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['reclass']), 1)

    def test_id_hors_batch_rejete(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'reclass': [
                        {'id': 'eZZ', 'signal': 'SEEN', 'confiance': 0.9}
                    ],
                    'proposition': None,
                }
            )
        )
        result = review_other_batch(
            self.conn, POLICY, ITEMS[:1], caller=caller
        )
        self.assertEqual(result['reclass'], [])
        self.assertTrue(result['fallback'])

    def test_killed_reste_other(self) -> None:
        caller = _caller_for('no json here {{{')
        result = review_other_batch(
            self.conn, POLICY, ITEMS[:1], caller=caller
        )
        self.assertEqual(result['reclass'], [])
        self.assertIsNone(result['proposition'])
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
