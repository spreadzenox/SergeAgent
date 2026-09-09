#!/usr/bin/env python3
"""Points H1/H2/H3 : rendu FR, intents owner, conséquence."""

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
from serge.points.interact import (  # noqa: E402
    classify_owner_intent,
    judge_consequence,
    render_context_fr,
    strip_ids,
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


class InteractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_strip_ids(self) -> None:
        self.assertEqual(strip_ids('ticket t_abc123def456 ok'), 'ticket  ok')
        self.assertEqual(strip_ids('rien ici'), 'rien ici')

    def test_rendu_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'titre': 'Valider le prix',
                    'ou': 'Proposition à 99 €.',
                    'enjeu': 'Marge venture.',
                    'attente': 'Approuver ou rejeter.',
                }
            )
        )
        result = render_context_fr(
            self.conn, POLICY, 'ticket QNA...', caller=caller
        )
        self.assertEqual(result['titre'], 'Valider le prix')
        self.assertEqual(result['fallback'], '')

    def test_rendu_repli_brut(self) -> None:
        caller = _caller_for('no json')
        result = render_context_fr(
            self.conn, POLICY, 'Ticket brut t_abc123def456', caller=caller
        )
        self.assertTrue(result['fallback'])
        self.assertIn('Ticket brut', result['titre'])

    def test_intent_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {'intent': 'APPROVE', 'confiance': 0.95, 'cible': 'prix'}
            )
        )
        result = classify_owner_intent(
            self.conn, POLICY, 'Oui, go pour 99 €.', caller=caller
        )
        self.assertEqual(
            (result['intent'], result['needs_clarify']),
            ('APPROVE', False),
        )

    def test_intent_ambigu_clarify(self) -> None:
        caller = _caller_for(
            json.dumps({'intent': 'ASK', 'confiance': 0.4, 'cible': ''})
        )
        result = classify_owner_intent(
            self.conn, POLICY, 'Hmm...', caller=caller
        )
        self.assertTrue(result['needs_clarify'])

    def test_consequence_oui(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'consequence': 'OUI',
                    'criteres': [{'nom': 'financier', 'touche': True}],
                    'confiance': 0.9,
                }
            )
        )
        result = judge_consequence(
            self.conn, POLICY, 'Rembourse 500 €.', caller=caller
        )
        self.assertTrue(result['needs_confirmation'])

    def test_consequence_non_sur(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'consequence': 'NON',
                    'criteres': [],
                    'confiance': 0.95,
                }
            )
        )
        result = judge_consequence(
            self.conn, POLICY, 'Montre-moi le digest.', caller=caller
        )
        self.assertFalse(result['needs_confirmation'])
        self.assertEqual(result['fallback'], '')


if __name__ == '__main__':
    unittest.main()
