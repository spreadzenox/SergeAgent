#!/usr/bin/env python3
"""Worker classify : O1 puis routage (opt-out, meeting, réponse)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402
from serge.workers.dispatch import execute  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {
        'classify_confidence_min': 0.6,
        'meeting_confidence_min': 0.8,
        'tech_fail_pattern_per_week': 3,
    },
    'windows': {'intent_biz_hours': [[8, 0, 20, 0]]},
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}
NOW = '2026-09-09T19:00:00+00:00'


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


class ClassifyWorkerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, regime,'
            " funnel_state, created_at, updated_at) VALUES('p1','v1','Ada',"
            " 'ada@x.io','OUTBOUND','CONTACTING','t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _event(self, event_id: str, text: str) -> None:
        self.conn.execute(
            'INSERT INTO inbound_events(id, campaign_id, contact_id, channel,'
            ' native_type, signal, received_at, payload_json)'
            " VALUES(?,'c1','p1','email','RECEIVED','REPLIED',?,?)",
            (event_id, NOW, json.dumps({'text': text})),
        )

    def _item(self, event_id: str) -> dict:
        item_id = enqueue(
            self.conn,
            kind='inbound.classify',
            idempotency_key=f'work:classify:{event_id}',
            venture_id='v1',
            payload={'event_id': event_id},
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        return claimed

    def test_question_vers_file_reponse(self) -> None:
        self._event('e1', 'Combien coûte votre offre ?')
        caller = _caller_for(
            json.dumps(
                {'classe': 'QUESTION', 'confiance': 0.9, 'requested': ''}
            )
        )
        result = execute(self.conn, POLICY, self._item('e1'), caller=caller)
        self.assertEqual(
            (result['status'], result['action']), ('done', 'reply_queued')
        )
        kinds = [
            row[0] for row in self.conn.execute('SELECT kind FROM work_items')
        ]
        self.assertIn('inbound.reply_priority', kinds)
        cls = self.conn.execute(
            'SELECT class FROM inbound_events WHERE id=?', ('e1',)
        ).fetchone()[0]
        self.assertEqual(cls, 'QUESTION')

    def test_opt_out_force(self) -> None:
        self._event('e2', 'Désinscrivez-moi immédiatement.')
        caller = _caller_for(
            json.dumps(
                {'classe': 'QUESTION', 'confiance': 0.9, 'requested': ''}
            )
        )
        result = execute(self.conn, POLICY, self._item('e2'), caller=caller)
        self.assertEqual(result['action'], 'opt_out')
        state = self.conn.execute(
            'SELECT funnel_state FROM contacts WHERE id=?', ('p1',)
        ).fetchone()[0]
        self.assertEqual(state, 'OPTED_OUT')

    def test_meeting_avec_creneau(self) -> None:
        self._event('e3', 'Un créneau 14h en visio ?')
        slot = (datetime.now().astimezone() + timedelta(days=1)).replace(
            hour=14, minute=0, second=0, microsecond=0
        )
        while slot.weekday() >= 5:  # week-end : pas de créneau (métier)
            slot += timedelta(days=1)
        slot_iso = slot.isoformat()
        caller = _caller_for(
            json.dumps(
                {
                    'classe': 'MEETING_REQUEST',
                    'confiance': 0.9,
                    'requested': '',
                }
            ),
            json.dumps(
                {
                    'datetime_iso': slot_iso,
                    'duree_min': 30,
                    'moyen': 'visio',
                    'confiance': 0.9,
                    'ambigu': False,
                }
            ),
        )
        result = execute(self.conn, POLICY, self._item('e3'), caller=caller)
        self.assertEqual(result['action'], 'reply_queued')
        payload = self.conn.execute(
            "SELECT payload_json FROM work_items WHERE kind='inbound.reply_priority'"
        ).fetchone()[0]
        self.assertIn(slot_iso, payload)

    def test_evenement_inconnu(self) -> None:
        result = execute(
            self.conn, POLICY, self._item('eZZ'), caller=_caller_for('{}')
        )
        self.assertEqual(result['error'], 'evenement_inconnu')

    def test_kind_inconnu(self) -> None:
        item_id = enqueue(
            self.conn,
            kind='nope.kind',
            idempotency_key='k-nope',
            venture_id='v1',
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        result = execute(self.conn, POLICY, claimed)
        self.assertIn('kind_inconnu', result['error'])


if __name__ == '__main__':
    unittest.main()
