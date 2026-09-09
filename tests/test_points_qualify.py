#!/usr/bin/env python3
"""Points P1/P7 : qualif prospects + score hybride."""

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
from serge.points.qualify import (  # noqa: E402
    det_score,
    icp_rules,
    qualify_prospect,
    score_lead,
)

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'prospection': {
        'qualify_confidence_min': 0.6,
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


class QualifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_regles_icp(self) -> None:
        self.assertEqual(
            icp_rules({'email': 'a@x.io'})['decision'], 'QUALIFIED'
        )
        self.assertEqual(icp_rules({'email': 'nope'})['decision'], 'REJECTED')
        self.assertEqual(
            icp_rules({'phone': '+33612345678'})['decision'], 'QUALIFIED'
        )

    def test_qualify_ok(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'decision': 'QUALIFIED',
                    'confiance': 0.85,
                    'motif': 'ICP match',
                    'requested': '',
                }
            )
        )
        result = qualify_prospect(
            self.conn,
            POLICY,
            'artisans FR',
            {'email': 'a@x.io'},
            caller=caller,
        )
        self.assertEqual(
            (result['decision'], result['needs_review']),
            ('QUALIFIED', False),
        )

    def test_qualify_sous_seuil_rejet(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'decision': 'QUALIFIED',
                    'confiance': 0.3,
                    'motif': 'bof',
                    'requested': 'secteur',
                }
            )
        )
        result = qualify_prospect(
            self.conn, POLICY, 'ICP', {'email': 'a@x.io'}, caller=caller
        )
        self.assertEqual(result['decision'], 'REJECTED')
        self.assertTrue(result['needs_review'])

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
