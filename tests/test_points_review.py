#!/usr/bin/env python3
"""Points B2/B3 : review fail-closed + dette dédupliquée."""

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
from serge.points.review import (  # noqa: E402
    review_build,
    summarize_build_debt,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'builder': {'fix_max_items': 5},
}


def _caller_for(*texts: str):
    calls: list = []

    def _call(*args, **kwargs):
        calls.append(args[2])
        index = min(len(calls) - 1, len(texts) - 1)
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.calls = calls  # type: ignore[attr-defined]
    return _call


class ReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_fix_localise(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'verdict': 'FIX',
                    'fix_items': [
                        {
                            'fichier': 'index.html',
                            'ligne': '12',
                            'probleme': 'CTA absent',
                            'suggestion': 'Ajouter.',
                        }
                    ],
                    'reserves': [],
                    'dette': [],
                    'justification': 'ok',
                }
            )
        )
        result = review_build(
            self.conn,
            POLICY,
            'spec',
            '<html/>',
            passe=1,
            images=['data:image/png;base64,xx'],
            caller=caller,
        )
        self.assertEqual(result['verdict'], 'FIX')
        self.assertEqual(len(result['fix_items']), 1)
        self.assertFalse(result['alert'])
        sent = caller.calls[0][1]['content']
        self.assertTrue(
            any(block.get('type') == 'image_url' for block in sent)
        )

    def test_passe3_binaire(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'verdict': 'FIX',
                    'fix_items': [],
                    'reserves': [],
                    'dette': [],
                    'justification': 'x',
                }
            )
        )
        result = review_build(
            self.conn, POLICY, 'spec', '<html/>', passe=3, caller=caller
        )
        self.assertEqual(result['action'], 'attente')
        self.assertTrue(result['alert'])

    def test_contradiction_flag(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'verdict': 'REBUILD',
                    'fix_items': [],
                    'reserves': [],
                    'dette': [],
                    'justification': '',
                }
            )
        )
        result = review_build(
            self.conn,
            POLICY,
            'spec',
            '<html/>',
            passe=2,
            prev_verdicts=['PASS'],
            caller=caller,
        )
        self.assertTrue(result['contradiction'])

    def test_killed_attente_alert(self) -> None:
        caller = _caller_for('no json')
        result = review_build(
            self.conn, POLICY, 'spec', '<html/>', caller=caller
        )
        self.assertEqual(result['action'], 'attente')
        self.assertTrue(result['alert'])
        self.assertIsNone(result['verdict'])

    def test_dette_dedup(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'dettes': [
                        {
                            'titre': 'CTA mobile',
                            'localisation': 'index.html',
                            'gravite': 'moyenne',
                            'suggestion': 'Revoir.',
                        },
                        {
                            'titre': 'CTA mobile',
                            'localisation': 'x',
                            'gravite': 'haute',
                            'suggestion': 'y',
                        },
                    ]
                }
            )
        )
        result = summarize_build_debt(
            self.conn, POLICY, 'verdict SHIP + réserves', caller=caller
        )
        self.assertEqual(len(result['dettes']), 1)
        self.assertEqual(result['fallback'], '')


if __name__ == '__main__':
    unittest.main()
