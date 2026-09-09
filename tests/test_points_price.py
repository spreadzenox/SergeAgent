#!/usr/bin/env python3
"""Point C1 : proposition prix, bornes + anti-garantie."""

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
from serge.points.price import draft_price  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'collect': {'draft_price_min_eur': 1.0, 'draft_price_max_eur': 1000.0},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


def _good(prix: float = 99.0, justif: str = 'Benchmarks 80-120.') -> str:
    return json.dumps(
        {
            'prix': prix,
            'alternatives': [79.0, 129.0],
            'justification': justif,
            'risques': ['Ancrage haut.'],
            'conditions_revision': 'Revoir à 50 clients.',
        }
    )


class PriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_propose_ok(self) -> None:
        caller = _caller_for(_good())
        result = draft_price(self.conn, POLICY, 'Audit email', caller=caller)
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(result['proposition']['prix'], 99.0)

    def test_hors_bornes_qna(self) -> None:
        caller = _caller_for(_good(5000.0))
        result = draft_price(self.conn, POLICY, 'Audit', caller=caller)
        self.assertEqual(result['action'], 'qna_brut')
        self.assertIn('hors_bornes', result['reason'])
        self.assertIn('offre', result['raw'])

    def test_garantie_rejetee(self) -> None:
        caller = _caller_for(_good(99.0, 'Je vous garantis 10 ventes.'))
        result = draft_price(self.conn, POLICY, 'Audit', caller=caller)
        self.assertEqual(result['action'], 'qna_brut')
        self.assertIn('engagement', result['reason'])

    def test_killed_qna(self) -> None:
        caller = _caller_for('no json')
        result = draft_price(self.conn, POLICY, 'Audit', caller=caller)
        self.assertEqual(result['action'], 'qna_brut')
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
