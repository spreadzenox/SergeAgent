#!/usr/bin/env python3
"""Worker email.send : rendu, guards, quota (retry), touch."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.email_gog import MailError  # noqa: E402
from serge.db.schema import init_schema  # noqa: E402
from serge.llm.client import ChatResult  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1, 'email_per_mailbox_per_day': 40},
    'observation': {'tech_fail_pattern_per_week': 3},
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}
NOW = '2026-09-09T10:00:00+00:00'


def _caller_for(*texts: str):
    def _call(*args, **kwargs):
        _call.n += 1  # type: ignore[attr-defined]
        index = min(_call.n - 1, len(texts) - 1)  # type: ignore[attr-defined]
        return ChatResult(texts[index], 10, 5, 'm', 3)

    _call.n = 0  # type: ignore[attr-defined]
    return _call


def _sender_ok(to: str, subject: str, body: str, **kwargs):
    _sender_ok.calls.append((to, subject, body))  # type: ignore[attr-defined]
    return {'message_id': 'm1', 'thread_id': ''}


_sender_ok.calls = []  # type: ignore[attr-defined]


class EmailSendTests(unittest.TestCase):
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
            " 'ada@x.io','OUTBOUND','QUALIFIED','t','t')"
        )
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, thresholds_json, created_at, updated_at)'
            " VALUES('c1','v1','named','email','RUNNING',50,?,?,?)",
            (
                json.dumps(
                    {'subject': 'Bonjour', 'template': 'Bonjour {nom} !'}
                ),
                NOW,
                NOW,
            ),
        )
        self.conn.commit()
        _sender_ok.calls.clear()

    def tearDown(self) -> None:
        self.conn.close()

    def _item(self, key: str, payload: dict, campaign: str = 'c1') -> dict:
        item_id = enqueue(
            self.conn,
            kind='email.send',
            idempotency_key=key,
            venture_id='v1',
            campaign_id=campaign,
            contact_id='p1',
            payload=payload,
        )
        claimed = claim(self.conn, item_id)
        assert claimed is not None
        return claimed

    def test_envoi_template_rendu(self) -> None:
        from serge.workers.send import run_email_send

        caller = _caller_for(
            json.dumps({'text': 'Bonjour Ada !', 'slots_used': ['nom']})
        )
        result = run_email_send(
            self.conn,
            POLICY,
            self._item('k-s1', {'step': 0}),
            caller=caller,
            sender=_sender_ok,
            now=NOW,
        )
        self.assertEqual(result['status'], 'done')
        self.assertEqual(_sender_ok.calls[0][1], 'Bonjour')

    def test_envoi_draft_direct(self) -> None:
        from serge.workers.send import run_email_send

        result = run_email_send(
            self.conn,
            POLICY,
            self._item(
                'k-s2',
                {'draft': 'Bonjour Ada !', 'subject': 'Hello'},
            ),
            sender=_sender_ok,
            now=NOW,
        )
        self.assertEqual(result['status'], 'done')
        self.assertEqual(_sender_ok.calls[0][0], 'ada@x.io')
        touch = self.conn.execute(
            'SELECT status, kind FROM touches'
        ).fetchone()
        self.assertEqual(tuple(touch), ('sent', 'send'))
        state = self.conn.execute(
            'SELECT funnel_state FROM contacts WHERE id=?', ('p1',)
        ).fetchone()[0]
        self.assertEqual(state, 'CONTACTING')

    def test_quota_retry_lendemain(self) -> None:
        from serge.workers.send import run_email_send

        policy = {
            **POLICY,
            'quotas': {**POLICY['quotas'], 'email_per_mailbox_per_day': 1},
        }
        run_email_send(
            self.conn,
            policy,
            self._item('k-q1', {'draft': 'Un', 'subject': 'S'}),
            sender=_sender_ok,
            now=NOW,
        )
        result = run_email_send(
            self.conn,
            policy,
            self._item('k-q2', {'draft': 'Deux', 'subject': 'S'}),
            sender=_sender_ok,
            now=NOW,
        )
        self.assertEqual(result['status'], 'retry')
        self.assertEqual(result['retry_at'], '2026-09-10T08:00:00+00:00')

    def test_guards_et_erreurs(self) -> None:
        from serge.privacy import subject_hash
        from serge.workers.send import run_email_send

        self.conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, reason,'
            " added_at) VALUES('b1','email',?,'owner',?)",
            (subject_hash('ada@x.io'), NOW),
        )
        result = run_email_send(
            self.conn,
            POLICY,
            self._item('k-g1', {'draft': 'X', 'subject': 'S'}),
            sender=_sender_ok,
            now=NOW,
        )
        self.assertIn('guards', result['error'])

        def _boom(*args, **kwargs):
            raise MailError('API: down')

        self.conn.execute('DELETE FROM blocklist')
        result = run_email_send(
            self.conn,
            POLICY,
            self._item('k-g2', {'draft': 'X', 'subject': 'S'}),
            sender=_boom,
            now=NOW,
        )
        self.assertIn('envoi', result['error'])
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, thresholds_json, created_at, updated_at)'
            " VALUES('c2','v1','named','email','RUNNING',50,'{}',?,?)",
            (NOW, NOW),
        )
        result = run_email_send(
            self.conn,
            POLICY,
            self._item('k-g3', {'draft': 'X'}, campaign='c2'),
            sender=_sender_ok,
            now=NOW,
        )
        self.assertEqual(result['error'], 'sujet_manquant')


if __name__ == '__main__':
    unittest.main()
