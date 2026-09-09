#!/usr/bin/env python3
"""Point O1 : classification réponses, garde-fous + repli."""

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
from serge.points.classify import (  # noqa: E402
    classify_reply,
    keyword_fallback,
    opt_out_suspect,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {'classify_confidence_min': 0.6},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class ClassifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_fallback_mots_cles(self) -> None:
        self.assertEqual(
            keyword_fallback('Merci de me désinscrire SVP')['classe'],
            'UNSUBSCRIBE',
        )
        self.assertEqual(
            keyword_fallback('On peut se faire un appel mardi ?')['classe'],
            'MEETING_REQUEST',
        )
        self.assertEqual(
            keyword_fallback('Cest trop cher pour nous')['classe'], 'OBJECTION'
        )
        self.assertEqual(
            keyword_fallback('Non merci, pas intéressé')['classe'], 'NEGATIVE'
        )
        self.assertEqual(
            keyword_fallback('Je suis absent jusquà lundi')['classe'],
            'AUTO_REPLY',
        )
        self.assertEqual(keyword_fallback('xxx yyyy zzz')['classe'], 'OTHER')
        self.assertTrue(opt_out_suspect('STOP, ne me contactez plus'))
        self.assertFalse(opt_out_suspect('Super, merci !'))

    def test_llm_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'classe': 'MEETING_REQUEST',
                    'confiance': 0.9,
                    'requested': '',
                }
            )
        )
        result = classify_reply(
            self.conn, POLICY, 'On se call mardi ?', caller=caller
        )
        self.assertEqual(
            (result['classe'], result['fallback'], result['needs_review']),
            ('MEETING_REQUEST', '', False),
        )
        self.assertFalse(result['opt_out'])

    def test_basse_confiance_review(self) -> None:
        caller = _caller_for(
            json.dumps(
                {'classe': 'QUESTION', 'confiance': 0.4, 'requested': 'x'}
            )
        )
        result = classify_reply(self.conn, POLICY, 'hmm ?', caller=caller)
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['requested'], 'x')

    def test_opt_out_force(self) -> None:
        caller = _caller_for(
            json.dumps(
                {'classe': 'QUESTION', 'confiance': 0.9, 'requested': ''}
            )
        )
        result = classify_reply(
            self.conn, POLICY, 'Désinscrivez-moi, merci', caller=caller
        )
        self.assertEqual(result['classe'], 'UNSUBSCRIBE')
        self.assertTrue(result['opt_out'])

    def test_invalide_repli(self) -> None:
        caller = _caller_for('{"classe": "X"}')
        result = classify_reply(
            self.conn, POLICY, 'On se call ?', caller=caller
        )
        self.assertEqual(result['classe'], 'MEETING_REQUEST')
        self.assertTrue(result['needs_review'])
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
