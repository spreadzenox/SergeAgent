#!/usr/bin/env python3
"""Points lecture seule : résumé thread + scoring appel."""

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
from serge.points.summaries import score_call, summarize_thread  # noqa: E402

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


class SummariesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_resume_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'resume': 'Prospect intéressé, frein prix.',
                    'statut': 'en_attente',
                    'next_step': 'Envoyer devis.',
                }
            )
        )
        result = summarize_thread(
            self.conn, POLICY, 'long thread', caller=caller
        )
        self.assertEqual(result['statut'], 'en_attente')
        self.assertEqual(result['fallback'], '')

    def test_resume_repli_brut(self) -> None:
        caller = _caller_for('pas json')
        result = summarize_thread(self.conn, POLICY, 'A' * 6000, caller=caller)
        self.assertTrue(result['fallback'])
        self.assertEqual(result['resume'], 'A' * 1500)

    def test_score_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'note': 2,
                    'flags': ['objection_non_traitee'],
                    'ecouter': True,
                }
            )
        )
        result = score_call(
            self.conn, POLICY, 'transcript...', 'durée 120s', caller=caller
        )
        self.assertEqual(
            (result['note'], result['flags'], result['ecouter']),
            (2, ['objection_non_traitee'], True),
        )

    def test_score_invalide_repli(self) -> None:
        caller = _caller_for(
            json.dumps({'note': 9, 'flags': [], 'ecouter': False})
        )
        result = score_call(self.conn, POLICY, 't', caller=caller)
        self.assertIsNone(result['note'])
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
