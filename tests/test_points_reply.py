#!/usr/bin/env python3
"""Point O3 : brouillon intent, filets engagement/prix, accusé repli."""

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
from serge.points.reply import (  # noqa: E402
    draft_intent_reply,
    engagement_hit,
    invented_numbers,
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


class ReplyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_detecteurs(self) -> None:
        self.assertEqual(
            engagement_hit('Nous vous garantissons le résultat'), 'garanti'
        )
        self.assertEqual(engagement_hit('Merci, à demain !'), '')
        self.assertEqual(invented_numbers('Ça coûte 99 €', 'offre 99 €'), [])
        self.assertEqual(
            invented_numbers('Ça coûte 199 €', 'offre 99 €'), ['199']
        )
        self.assertEqual(invented_numbers('Bonjour !', ''), [])

    def test_envoi_propre(self) -> None:
        caller = _caller_for(
            json.dumps({'draft': 'Merci ! On se call ?', 'confiance': 0.9})
        )
        result = draft_intent_reply(
            self.conn,
            POLICY,
            'historique',
            'QUESTION 0.9',
            'Bonjour ?',
            caller=caller,
        )
        self.assertEqual(result['action'], 'send')
        self.assertEqual(result['fallback'], '')

    def test_engagement_vers_ticket(self) -> None:
        caller = _caller_for(
            json.dumps(
                {'draft': 'Je vous garantis 10 clients.', 'confiance': 0.9}
            )
        )
        result = draft_intent_reply(
            self.conn, POLICY, '', 'POSITIVE 0.9', 'Go !', caller=caller
        )
        self.assertEqual(result['action'], 'ticket')
        self.assertIn('engagement', result['reason'])

    def test_prix_invente_vers_ticket(self) -> None:
        caller = _caller_for(
            json.dumps({'draft': 'Notre offre est à 499 €.', 'confiance': 0.9})
        )
        result = draft_intent_reply(
            self.conn,
            POLICY,
            '',
            'QUESTION 0.9',
            'Combien ?',
            offer_text='offre à 99 €',
            caller=caller,
        )
        self.assertEqual(result['action'], 'ticket')
        self.assertIn('nombres', result['reason'])

    def test_killed_accuse(self) -> None:
        caller = _caller_for('pas du json {{{')
        result = draft_intent_reply(
            self.conn, POLICY, '', 'X', 'Bonjour', caller=caller
        )
        self.assertEqual(result['action'], 'ticket')
        self.assertTrue(result['fallback'])
        self.assertIn('reviens vers vous', result['draft'])


if __name__ == '__main__':
    unittest.main()
