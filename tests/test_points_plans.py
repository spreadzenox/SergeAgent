#!/usr/bin/env python3
"""Points M3/M4/M5 : plans scale, pivots, résumés chiffrés."""

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
from serge.points.plans import (  # noqa: E402
    options_pivot,
    plan_scale,
    resume_test,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class PlansTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_scale_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'volumes': 'x2',
                    'canaux': ['email'],
                    'budget_eur': 100.0,
                    'builder': ['landing'],
                    'jalons': ['J7'],
                    'risques': ['trunk'],
                    'justification': 'Car ça marche.',
                }
            )
        )
        result = plan_scale(
            self.conn, POLICY, 'full U3=12', 'budget 200', caller=caller
        )
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(result['plan']['budget_eur'], 100.0)

    def test_scale_killed_replay(self) -> None:
        caller = _caller_for('no json')
        result = plan_scale(self.conn, POLICY, 'full', 'b', caller=caller)
        self.assertEqual(result['action'], 'replay')
        self.assertIsNone(result['plan'])

    def test_pivot_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'options': [
                        {
                            'changement': 'cible PME',
                            'rationnel': 'r',
                            'risque': 'q',
                            'dimensions_changees': ['cible'],
                            'pre_enregistrement': 'N=40',
                        },
                        {
                            'changement': 'canal voix',
                            'rationnel': 'r',
                            'risque': 'q',
                            'dimensions_changees': ['canal'],
                            'pre_enregistrement': 'N=40',
                        },
                    ]
                }
            )
        )
        result = options_pivot(self.conn, POLICY, 'trop cher', caller=caller)
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(len(result['options']), 2)

    def test_pivot_sans_diff_extend(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'options': [
                        {
                            'changement': 'pareil',
                            'rationnel': 'r',
                            'risque': 'q',
                            'dimensions_changees': [],
                            'pre_enregistrement': 'N=40',
                        },
                        {
                            'changement': 'idem',
                            'rationnel': 'r',
                            'risque': 'q',
                            'dimensions_changees': ['canal'],
                            'pre_enregistrement': 'N=40',
                        },
                    ]
                }
            )
        )
        result = options_pivot(self.conn, POLICY, 'obj', caller=caller)
        self.assertEqual(result['action'], 'extend')

    def test_resume_chiffres_verifies(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'resume': 'U1=40, U3=3, verdict FULL.',
                    'apprentissages': ['Le prix freine.'],
                    'suites': 'Full email.',
                }
            )
        )
        result = resume_test(
            self.conn, POLICY, 'U1=40, U3=3', 'verdict=FULL', caller=caller
        )
        self.assertEqual(result['fallback'], '')
        bad = _caller_for(
            json.dumps(
                {
                    'resume': 'U1=40, U3=99, verdict FULL.',
                    'apprentissages': [],
                    'suites': '',
                }
            )
        )
        result = resume_test(
            self.conn, POLICY, 'U1=40, U3=3', 'verdict=FULL', caller=bad
        )
        self.assertIn('nombres', result['fallback'])


if __name__ == '__main__':
    unittest.main()
