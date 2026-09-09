#!/usr/bin/env python3
"""Points P2/P3 : slots + follow-ups, checkers + regen + brut."""

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
from serge.points.checkers import (  # noqa: E402
    check_aggressivity,
    check_forbidden,
    check_length,
)
from serge.points.write import fill_slots, write_followup  # noqa: E402

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


class WriteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_checkers(self) -> None:
        self.assertEqual(check_length('ok', 10), '')
        self.assertEqual(check_length('', 10), 'vide')
        self.assertTrue(check_length('x' * 11, 10).startswith('trop_long'))
        self.assertEqual(check_forbidden('Bonjour', ['garanti']), '')
        self.assertEqual(
            check_forbidden('Cest garanti !', ['garanti']), 'garanti'
        )
        self.assertEqual(check_aggressivity('Merci, à bientôt !'), '')
        self.assertEqual(
            check_aggressivity('Dernière chance avant cloture.'),
            'derniere chance',
        )

    def test_slots_ok(self) -> None:
        caller = _caller_for(
            json.dumps({'text': 'Bonjour Ada !', 'slots_used': ['prenom']})
        )
        result = fill_slots(
            self.conn,
            POLICY,
            'Bonjour {prenom} !',
            'prenom=Ada',
            caller=caller,
        )
        self.assertEqual(
            (result['text'], result['action']), ('Bonjour Ada !', 'send')
        )

    def test_slots_interdit_regen(self) -> None:
        caller = _caller_for(
            json.dumps({'text': 'Cest garanti !', 'slots_used': []}),
            json.dumps({'text': 'Bonjour !', 'slots_used': []}),
        )
        result = fill_slots(
            self.conn,
            POLICY,
            'Bonjour !',
            'fiche',
            forbidden=['garanti'],
            caller=caller,
        )
        self.assertEqual(result['text'], 'Bonjour !')
        self.assertIn('regen', result['reason'])

    def test_slots_killed_brut(self) -> None:
        caller = _caller_for('no json')
        result = fill_slots(
            self.conn, POLICY, 'Bonjour {x} !', 'fiche', caller=caller
        )
        self.assertEqual(result['action'], 'template_brut')
        self.assertEqual(result['text'], 'Bonjour {x} !')

    def test_followup_agressif_generique(self) -> None:
        caller = _caller_for(
            json.dumps({'text': 'Dernière chance, répondez !'}),
            json.dumps({'text': 'Sans réponse de votre part...'}),
        )
        result = write_followup(self.conn, POLICY, 'historique', caller=caller)
        self.assertEqual(result['action'], 'template_generique')
        self.assertIn('clore le dossier', result['text'])


if __name__ == '__main__':
    unittest.main()
