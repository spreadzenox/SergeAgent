#!/usr/bin/env python3
"""Points M1/M2 : hypothèses smoke/full, schéma dét + template."""

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
from serge.points.hypotheses import (  # noqa: E402
    draft_hypothesis,
    validate_hypothesis,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
}
GOOD_SMOKE = {
    'hypothese': 'Les artisans répondent à l\u2019email.',
    'N': 40,
    'canaux': ['email'],
    'seuils': {'scale_min_positifs': 3},
    'fenetre_jours': 7,
    'prix_draft': '29-49€',
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class HypothesesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_schema(self) -> None:
        self.assertEqual(validate_hypothesis(GOOD_SMOKE, 'smoke'), '')
        bad_n = dict(GOOD_SMOKE)
        bad_n['N'] = 200
        self.assertTrue(validate_hypothesis(bad_n, 'smoke'))
        bad_f = dict(GOOD_SMOKE)
        bad_f['fenetre_jours'] = 30
        self.assertTrue(validate_hypothesis(bad_f, 'smoke'))
        self.assertTrue(validate_hypothesis(GOOD_SMOKE, 'full'))
        self.assertTrue(validate_hypothesis({}, 'smoke'))
        self.assertTrue(validate_hypothesis(GOOD_SMOKE, 'nope'))

    def test_smoke_ok(self) -> None:
        caller = _caller_for(json.dumps(GOOD_SMOKE))
        result = draft_hypothesis(
            self.conn, POLICY, 'smoke', ecoute_text='signaux', caller=caller
        )
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(result['hypothese']['N'], 40)

    def test_schema_rejete_template(self) -> None:
        bad = dict(GOOD_SMOKE)
        bad['N'] = 5000
        caller = _caller_for(json.dumps(bad))
        result = draft_hypothesis(self.conn, POLICY, 'smoke', caller=caller)
        self.assertEqual(result['action'], 'template_min')
        self.assertEqual(result['hypothese']['N'], 30)

    def test_killed_template(self) -> None:
        caller = _caller_for('no json')
        result = draft_hypothesis(
            self.conn, POLICY, 'full', smoke_text='U1=40', caller=caller
        )
        self.assertEqual(result['action'], 'template_min')
        self.assertEqual(result['hypothese']['N'], 150)
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
