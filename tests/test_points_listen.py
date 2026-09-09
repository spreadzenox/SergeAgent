#!/usr/bin/env python3
"""Point J1 : labels + scores clusters demande."""

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
from serge.points.listen_pts import label_clusters  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
}
CLUSTERS = [
    {'id': 'k1', 'verbatims': ['Trop cher...', 'Facture salée...']},
    {'id': 'k2', 'verbatims': ['Cherche outil email...']},
]


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class ListenPointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_labels_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'clusters': [
                        {
                            'id': 'k1',
                            'label': 'Douleur prix',
                            'volume': 0.8,
                            'intensite': 0.7,
                            'recurrence': 0.6,
                            'willingness': 0.9,
                            'opportunite_chaude': True,
                        }
                    ]
                }
            )
        )
        result = label_clusters(self.conn, POLICY, CLUSTERS, caller=caller)
        self.assertEqual(result['clusters'][0]['label'], 'Douleur prix')
        self.assertTrue(result['clusters'][0]['opportunite_chaude'])
        self.assertEqual(result['fallback'], '')

    def test_id_inconnu_rejet(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'clusters': [
                        {
                            'id': 'kZZ',
                            'label': 'X',
                            'volume': 0.5,
                            'intensite': 0.5,
                            'recurrence': 0.5,
                            'willingness': 0.5,
                            'opportunite_chaude': False,
                        }
                    ]
                }
            )
        )
        result = label_clusters(self.conn, POLICY, CLUSTERS, caller=caller)
        self.assertEqual(result['clusters'][0]['label'], '')
        self.assertTrue(result['fallback'])


if __name__ == '__main__':
    unittest.main()
