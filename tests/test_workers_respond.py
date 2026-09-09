#!/usr/bin/env python3
"""Workers reply + judge_other : envois gatés, tickets, reclassements."""

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
from serge.workers.dispatch import execute  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {
        'classify_confidence_min': 0.6,
        'meeting_confidence_min': 0.8,
        'tech_fail_pattern_per_week': 3,
        'other_batch_max_items': 20,
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


class RespondWorkerTests(unittest.TestCase):
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
            " 'ada@x.io','INBOUND','ENGAGED','t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _event(self, event_id: str, text: str, signal: str = 'INTENT') -> None:
        self.conn.execute(
            'INSERT INTO inbound_events(id, campaign_id, contact_id, channel,'
            ' native_type, signal, received_at, payload_json)'
            " VALUES(?,'c1','p1','email','RECEIVED',?,?,?)",
            (event_id, signal, NOW, json.dumps({'text': text})),
        )

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

    def test_reponse_envoyee_en_file(self) -> None:
        self._event('e1', 'Combien coûte votre offre ?')
        caller = _caller_for(
            json.dumps({'draft': 'Merci ! On se call ?', 'confiance': 0.9})
        )
        result = execute(
            self.conn,
            POLICY,
            self._item(
                'inbound.reply_priority',
                'k-r1',
                {'event_id': 'e1', 'classe': 'QUESTION'},
            ),
            caller=caller,
        )
        self.assertEqual(
            (result['status'], result['action']), ('done', 'sent_queued')
        )
        kinds = [
            row[0] for row in self.conn.execute('SELECT kind FROM work_items')
        ]
        self.assertIn('email.send', kinds)

    def test_engagement_vers_ticket(self) -> None:
        self._event('e2', 'Go !')
        caller = _caller_for(
            json.dumps(
                {'draft': 'Je vous garantis 10 clients.', 'confiance': 0.9}
            )
        )
        result = execute(
            self.conn,
            POLICY,
            self._item(
                'inbound.reply_priority',
                'k-r2',
                {'event_id': 'e2', 'classe': 'POSITIVE'},
            ),
            caller=caller,
        )
        self.assertEqual(result['action'], 'ticket')
        state = self.conn.execute(
            'SELECT state FROM tickets WHERE id=?', (result['ticket_id'],)
        ).fetchone()[0]
        self.assertEqual(state, 'OPEN')

    def test_guards_bloque_vers_ticket(self) -> None:
        from serge.privacy import subject_hash

        self._event('e3', 'Bonjour ?')
        self.conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1','email',?,'owner',?)",
            (subject_hash('ada@x.io'), NOW),
        )
        caller = _caller_for(
            json.dumps({'draft': 'Bonjour Ada !', 'confiance': 0.9})
        )
        result = execute(
            self.conn,
            POLICY,
            self._item(
                'inbound.reply_priority',
                'k-r3',
                {'event_id': 'e3', 'classe': 'QUESTION'},
            ),
            caller=caller,
        )
        self.assertEqual(result['action'], 'ticket')

    def test_juge_reclasse_et_propose(self) -> None:
        self._event('o1', 'bla bla', signal='OTHER')
        self._event('o2', 'bli bli', signal='OTHER')
        caller = _caller_for(
            json.dumps(
                {
                    'reclass': [
                        {'id': 'o1', 'signal': 'INTENT', 'confiance': 0.9},
                        {'id': 'o2', 'signal': 'OTHER', 'confiance': 0.4},
                    ],
                    'proposition': {'nom': 'X', 'definition': 'y'},
                }
            )
        )
        result = execute(
            self.conn,
            POLICY,
            self._item('inbound.judge_other', 'k-j1', {}),
            caller=caller,
        )
        self.assertEqual((result['applied'], result['stayed']), (1, 1))
        self.assertTrue(result['ticket_id'])
        kinds = [
            row[0] for row in self.conn.execute('SELECT kind FROM work_items')
        ]
        self.assertIn('inbound.reply_priority', kinds)
        signal = self.conn.execute(
            'SELECT signal FROM inbound_events WHERE id=?', ('o2',)
        ).fetchone()[0]
        self.assertEqual(signal, 'OTHER')


if __name__ == '__main__':
    unittest.main()
