#!/usr/bin/env python3
"""Smoke live LLM (live-prudent) : O1 réel via OpenRouter.

Skippé hors SERGE_ENV=test + OPENROUTER_API_KEY. 3 appels max (point +
recalls). Prouve le chemin runtime complet (slots → appel → metering).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.points.classify import CLASSES, classify_reply  # noqa: E402
from serge.policy import load_policy  # noqa: E402
from serge.testkit import SessionCap, require_live, temp_canon  # noqa: E402


class LiveLlmTests(unittest.TestCase):
    def test_classify_reel(self) -> None:
        require_live()
        key = os.environ.get('OPENROUTER_API_KEY', '').strip()
        if not key:
            self.skipTest('OPENROUTER_API_KEY requise')
        cap = SessionCap(3)
        policy = load_policy()
        with tempfile.TemporaryDirectory(prefix='serge-llm-') as raw:
            root = Path(raw)
            (root / 'llm').mkdir()
            (root / 'secrets').mkdir()
            (root / 'llm/slots.json').write_text(
                json.dumps(
                    {
                        'referer': 'https://serge.test',
                        'slots': {
                            'CHEAP': {'openrouter_id': 'xiaomi/mimo-v2.5'}
                        },
                    }
                ),
                encoding='utf-8',
            )
            (root / 'secrets/openrouter-api-key').write_text(
                key + '\n', encoding='utf-8'
            )
            with temp_canon() as (conn, _):
                cap.spend('classify_reply')
                result = classify_reply(
                    conn,
                    policy,
                    'Bonjour, on peut se faire un appel mardi ?',
                    root=root,
                )
                self.assertEqual(result['fallback'], '')
                self.assertIn(result['classe'], CLASSES)
                rows = conn.execute(
                    "SELECT verdict FROM llm_usage WHERE point='classify_reply'"
                ).fetchall()
                self.assertTrue(rows)
                conn.commit()


if __name__ == '__main__':
    unittest.main()
