#!/usr/bin/env python3
"""Workers écoute : collecte flux + batch clusters → FYI chaud."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.listen.collectors import ListenError  # noqa: E402
from serge.listen.memory import create_cycle  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402
from serge.workers.dispatch import execute  # noqa: E402
from serge.workers.listen import run_business_cycle  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'listen': {
        'hot_min_volume': 0.7,
        'hot_min_willingness': 0.7,
        'cluster_jaccard_min': 0.25,
    },
}
DOCS = [
    {
        'id': 'ld_a',
        'source': 'f',
        'title': 'Facture artisan trop chère',
        'url': 'https://f.test/a',
        'excerpt': 'Les artisans se plaignent des factures salées.',
        'published': '',
    },
    {
        'id': 'ld_b',
        'source': 'f',
        'title': 'Artisans : factures salées',
        'url': 'https://f.test/b',
        'excerpt': 'La facture des artisans augmente encore, trop chère.',
        'published': '',
    },
]


class _ScriptedCaller:
    def __init__(self, texts: tuple[str, ...]) -> None:
        self.texts = texts
        self.n = 0

    def __call__(self, *args: Any, **kwargs: Any) -> ChatResult:
        del args, kwargs
        self.n += 1
        index = min(self.n - 1, len(self.texts) - 1)
        return ChatResult(self.texts[index], 10, 5, 'm', 3)


def _caller_for(*texts: str) -> _ScriptedCaller:
    return _ScriptedCaller(texts)


class ListenWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _item(self, kind: str, key: str, payload: dict) -> dict:
        item_id = enqueue(
            self.conn,
            kind=kind,
            idempotency_key=key,
            venture_id='v1',
            payload=payload,
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        return claimed

    def test_collecte(self) -> None:
        with mock.patch(
            'serge.workers.listen.fetch_rss', return_value=list(DOCS)
        ):
            result = execute(
                self.conn,
                POLICY,
                self._item(
                    'listen.collect',
                    'k-lc',
                    {'feeds': [{'url': 'https://f.test/rss', 'source': 'f'}]},
                ),
            )
        self.assertEqual((result['status'], result['new']), ('done', 2))
        self.assertEqual(result['errors'], [])

    def test_collecte_erreur_par_flux(self) -> None:
        def _boom(url: str, source: str):
            raise ListenError('NETWORK: down')

        with mock.patch('serge.workers.listen.fetch_rss', side_effect=_boom):
            result = execute(
                self.conn,
                POLICY,
                self._item(
                    'listen.collect',
                    'k-le',
                    {'feeds': [{'url': 'https://x/rss', 'source': 'x'}]},
                ),
            )
        self.assertEqual(result['status'], 'done')
        self.assertEqual(len(result['errors']), 1)

    def test_cluster_chaud_fyi(self) -> None:
        with mock.patch(
            'serge.workers.listen.fetch_rss', return_value=list(DOCS)
        ):
            execute(
                self.conn,
                POLICY,
                self._item(
                    'listen.collect',
                    'k-lc2',
                    {'feeds': [{'url': 'https://f.test/rss', 'source': 'f'}]},
                ),
            )
        caller = _caller_for(
            json.dumps(
                {
                    'clusters': [
                        {
                            'id': 'k1',
                            'label': 'Douleur prix artisans',
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
        result = execute(
            self.conn,
            POLICY,
            self._item('listen.cluster', 'k-lk', {}),
            caller=caller,
        )
        self.assertEqual((result['clusters'], result['hot']), (1, 1))
        self.assertTrue(result['ticket_id'])
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (result['ticket_id'],)
        ).fetchone()[0]
        self.assertEqual(state, 'OPEN')

    def test_cluster_vide(self) -> None:
        caller = _caller_for('{}')
        result = execute(
            self.conn,
            POLICY,
            self._item('listen.cluster', 'k-lv', {}),
            caller=caller,
        )
        self.assertEqual(result['clusters'], 0)
        self.assertEqual(caller.n, 0)

    def test_cycle_business_invoque_a_et_b_sur_le_meme_contrat(self) -> None:
        cycle_id = create_cycle(self.conn, 'guide', 5, 1)
        caller = _caller_for(
            json.dumps(
                {
                    'needs': [
                        {
                            'title': 'Besoin A',
                            'content': 'Contenu A',
                            'evidence_ids': [],
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    'needs': [
                        {
                            'title': 'Besoin B',
                            'content': 'Contenu B',
                            'evidence_ids': [],
                        }
                    ]
                }
            ),
            '{"candidate_ids": []}',
        )
        result = run_business_cycle(
            self.conn,
            POLICY,
            {'payload_json': json.dumps({'cycle_id': cycle_id})},
            caller=caller,
        )
        self.assertEqual(result['llm'], [True, True, True])
        self.assertEqual(
            [
                row[0]
                for row in self.conn.execute(
                    'SELECT point FROM llm_usage ORDER BY rowid'
                )
            ],
            [
                'listen_discover_needs_a',
                'listen_discover_needs_b',
                'listen_choose_poc',
            ],
        )


if __name__ == '__main__':
    unittest.main()
