#!/usr/bin/env python3
"""Point P4 : script voix, disclosure + durée + pinné."""

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
from serge.points.voice_script import (  # noqa: E402
    check_disclosure,
    draft_voice_script,
    estimate_duration_s,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'voice': {'script_max_seconds': 120},
}
PINNED = [{'nom': 'accroche', 'texte': 'Bonjour, ici Serge.'}]


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class VoiceScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_checkers(self) -> None:
        self.assertEqual(
            check_disclosure(
                [
                    {
                        'nom': 'a',
                        'texte': 'Je suis Serge, un assistant vocal IA.',
                    }
                ]
            ),
            '',
        )
        self.assertEqual(
            check_disclosure([{'nom': 'a', 'texte': 'Bonjour !'}]),
            'disclosure_manquante',
        )
        self.assertIn(
            'passing_humain',
            check_disclosure(
                [
                    {
                        'nom': 'a',
                        'texte': 'Je suis Serge, un assistant vocal, une vraie personne.',
                    }
                ]
            ),
        )
        self.assertEqual(estimate_duration_s([{'texte': 'x' * 130}]), 10)

    def test_propose_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'blocs': [
                        {
                            'nom': 'accroche',
                            'texte': 'Bonjour, je suis Serge, un assistant vocal IA.',
                        },
                        {'nom': 'cloture', 'texte': 'Bonne journée !'},
                    ]
                }
            )
        )
        result = draft_voice_script(
            self.conn, POLICY, 'fiche', pinned=PINNED, caller=caller
        )
        self.assertEqual(result['action'], 'propose')
        self.assertEqual(result['fallback'], '')
        self.assertGreater(result['duree_totale_s'], 0)

    def test_sans_disclosure_pinned(self) -> None:
        caller = _caller_for(
            json.dumps({'blocs': [{'nom': 'a', 'texte': 'Bonjour !'}]})
        )
        result = draft_voice_script(
            self.conn, POLICY, 'fiche', pinned=PINNED, caller=caller
        )
        self.assertEqual(result['action'], 'pinned')
        self.assertEqual(result['blocs'], PINNED)
        self.assertIn('disclosure', result['reason'])

    def test_trop_long_pinned(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'blocs': [
                        {
                            'nom': 'a',
                            'texte': 'Je suis Serge, un assistant vocal IA. '
                            + 'bla ' * 600,
                        }
                    ]
                }
            )
        )
        result = draft_voice_script(
            self.conn, POLICY, 'fiche', pinned=PINNED, caller=caller
        )
        self.assertEqual(result['action'], 'pinned')
        self.assertIn('trop_long', result['reason'])

    def test_killed_sans_pinned_vide(self) -> None:
        caller = _caller_for('no json')
        result = draft_voice_script(self.conn, POLICY, 'fiche', caller=caller)
        self.assertEqual(result['action'], 'pinned')
        self.assertEqual(result['blocs'], [])


if __name__ == '__main__':
    unittest.main()
