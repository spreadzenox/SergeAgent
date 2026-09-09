#!/usr/bin/env python3
"""Points D1/D2 : consolidation batch + SERGE.md borné."""

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
from serge.points.memory_pts import consolidate, edit_serge_md  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'memory': {'consolidate_max_items': 10, 'serge_md_max_lines': 100},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class MemoryPointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_consolidate_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'lecons': [
                        {
                            'enonce': 'Relancer J+3 double les réponses.',
                            'confiance': 0.7,
                            'sources': ['e1', 'e2'],
                            'scope': 'canal',
                        }
                    ],
                    'playbooks': [],
                    'pitfalls': [
                        {'enonce': 'Appeler le lundi matin.', 'cout': '2/5'}
                    ],
                }
            )
        )
        result = consolidate(self.conn, POLICY, 'épisodes...', caller=caller)
        self.assertEqual(len(result['lecons']), 1)
        self.assertEqual(len(result['pitfalls']), 1)
        self.assertEqual(result['fallback'], '')

    def test_consolidate_sans_source_rejet(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'lecons': [
                        {
                            'enonce': 'X.',
                            'confiance': 0.9,
                            'sources': [],
                            'scope': 'global',
                        }
                    ],
                    'playbooks': [],
                    'pitfalls': [],
                }
            )
        )
        result = consolidate(self.conn, POLICY, 'eps', caller=caller)
        self.assertEqual(result['lecons'], [])
        self.assertTrue(result['fallback'])

    def test_serge_md_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'serge_md': '# Serge\nVenture : v1\n',
                    'changements': ['venture active'],
                }
            )
        )
        result = edit_serge_md(
            self.conn, POLICY, '# Serge\n', 'nouvelle venture', caller=caller
        )
        self.assertIn('v1', result['serge_md'])
        self.assertEqual(result['fallback'], '')

    def test_serge_md_trop_long_repli(self) -> None:
        long_md = '\n'.join(f'ligne {index}' for index in range(200))
        caller = _caller_for(
            json.dumps({'serge_md': long_md, 'changements': []})
        )
        result = edit_serge_md(
            self.conn, POLICY, '# Serge\n', 'x', caller=caller
        )
        self.assertEqual(result['serge_md'], '# Serge\n')
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
