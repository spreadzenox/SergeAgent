#!/usr/bin/env python3
"""Qualité voix : scores, fenêtre glissante, gate pause, worker."""

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
from serge.scheduler import claim, enqueue  # noqa: E402
from serge.voice.quality import (  # noqa: E402
    check_voice_quality,
    record_call_score,
)
from serge.workers.dispatch import execute  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'voice': {
        'quality_window': 4,
        'quality_min_score': 2,
        'quality_max_bad': 2,
    },
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class VoiceQualityTests(unittest.TestCase):
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

    def test_gate_ok_puis_pause(self) -> None:
        record_call_score(self.conn, 'c1', 5, [], False)
        record_call_score(self.conn, 'c2', 4, [], False)
        gate = check_voice_quality(self.conn, POLICY)
        self.assertEqual((gate['action'], gate['bad']), ('ok', 0))
        record_call_score(self.conn, 'c3', 2, ['derive'], True)
        gate = check_voice_quality(self.conn, POLICY)
        self.assertEqual(gate['action'], 'ok')
        record_call_score(self.conn, 'c4', 1, ['x'], True)
        gate = check_voice_quality(self.conn, POLICY)
        self.assertEqual(gate['action'], 'pause')
        self.assertIn('2 notes', gate['reason'])

    def test_worker_score(self) -> None:
        caller = _caller_for(
            json.dumps({'note': 4, 'flags': [], 'ecouter': False})
        )
        item_id = enqueue(
            self.conn,
            kind='voice.score',
            idempotency_key='k-vs',
            venture_id='v1',
            payload={'cdr_id': 'c9', 'transcript': 'Bonjour...'},
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        result = execute(self.conn, POLICY, claimed, caller=caller)
        self.assertEqual(
            (result['status'], result['note'], result['gate']),
            ('done', 4, 'ok'),
        )


if __name__ == '__main__':
    unittest.main()
