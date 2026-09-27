#!/usr/bin/env python3
"""Point P7 : score de piste déterministe + départage en zone grise."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.points.score_lead import (  # noqa: E402
    det_score,
    score_lead,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'prospection': {
        'lead_score_gray': [40, 60],
        'score_w_intent': 25,
        'score_w_reply': 10,
        'score_w_engaged': 5,
        'score_w_meeting': 40,
        'score_w_negative': -20,
    },
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class ScoreLeadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_det_score_zones(self) -> None:
        self.assertEqual(det_score(self.conn, POLICY, 'p0')['zone'], 'low')
        for index in range(2):
            self.conn.execute(
                'INSERT INTO inbound_events(id, contact_id, channel,'
                ' native_type, signal, received_at)'
                " VALUES(?,'p1','email','X','INTENT',?)",
                (f'e{index}', '2026-09-09T00:00:00+00:00'),
            )
        scored = det_score(self.conn, POLICY, 'p1')
        self.assertEqual((scored['score'], scored['zone']), (50, 'gray'))
        for index in range(4):
            self.conn.execute(
                'INSERT INTO inbound_events(id, contact_id, channel,'
                ' native_type, signal, received_at)'
                " VALUES(?,'p2','email','X','INTENT',?)",
                (f'f{index}', '2026-09-09T00:00:00+00:00'),
            )
        self.assertEqual(det_score(self.conn, POLICY, 'p2')['zone'], 'high')

    def test_departage_gris_couteux(self) -> None:
        self.conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel,'
            " native_type, signal, received_at) VALUES('e0','p1','email',"
            "'X','INTENT','2026-09-09T00:00:00+00:00')"
        )
        self.conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel,'
            " native_type, signal, received_at) VALUES('e1','p1','email',"
            "'X','REPLIED','2026-09-09T00:00:00+00:00')"
        )
        self.conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel,'
            " native_type, signal, received_at) VALUES('e2','p1','email',"
            "'X','ENGAGED','2026-09-09T00:00:00+00:00')"
        )
        caller = _caller_for(
            json.dumps(
                {'decision': 'allouer', 'confiance': 0.7, 'motif': 'chaud'}
            )
        )
        result = score_lead(
            self.conn, POLICY, 'p1', 'historique', costly=True, caller=caller
        )
        self.assertEqual(
            (result['score'], result['zone'], result['decision']),
            (40, 'gray', 'allouer'),
        )
        plain = score_lead(self.conn, POLICY, 'p1')
        self.assertEqual(plain['decision'], 'revoir')


if __name__ == '__main__':
    unittest.main()
