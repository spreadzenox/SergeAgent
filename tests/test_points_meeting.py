#!/usr/bin/env python3
"""Point O2 : extraction créneau, vérif dét + clarification."""

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
from serge.points.meeting import extract_meeting  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {'meeting_confidence_min': 0.8},
    'windows': {'intent_biz_hours': [[8, 0, 20, 0]]},
}


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class MeetingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_ok_futur_ouvre(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'datetime_iso': '2026-09-10T14:00:00+02:00',
                    'duree_min': 30,
                    'moyen': 'visio',
                    'confiance': 0.9,
                    'ambigu': False,
                }
            )
        )
        result = extract_meeting(
            self.conn,
            POLICY,
            'Jeudi 14h en visio ?',
            now_iso='2026-09-09T10:00:00+02:00',
            caller=caller,
        )
        self.assertEqual(result['action'], 'propose_booking')
        self.assertEqual(result['datetime_iso'], '2026-09-10T14:00:00+02:00')

    def test_passe_dimanche_clarify(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'datetime_iso': '2026-09-06T14:00:00+02:00',
                    'duree_min': 30,
                    'moyen': 'appel',
                    'confiance': 0.95,
                    'ambigu': False,
                }
            )
        )
        result = extract_meeting(
            self.conn,
            POLICY,
            'dimanche ?',
            now_iso='2026-09-09T10:00:00+02:00',
            caller=caller,
        )
        self.assertEqual(result['action'], 'clarify')
        self.assertIsNone(result['datetime_iso'])

    def test_ambigu_clarify(self) -> None:
        caller = _caller_for(
            json.dumps(
                {
                    'datetime_iso': '2026-09-10T14:00:00+02:00',
                    'duree_min': 30,
                    'moyen': 'appel',
                    'confiance': 0.9,
                    'ambigu': True,
                }
            )
        )
        result = extract_meeting(
            self.conn,
            POLICY,
            'demain ou jeudi ?',
            now_iso='2026-09-09T10:00:00+02:00',
            caller=caller,
        )
        self.assertEqual(result['action'], 'clarify')
        self.assertTrue(result['ambigu'])


if __name__ == '__main__':
    unittest.main()
