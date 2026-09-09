#!/usr/bin/env python3
"""Workers voice.send (broker) + email.poll (Gmail → ingest)."""

from __future__ import annotations

import base64
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.email_gog import MailError  # noqa: E402
from serge.db.schema import init_schema  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402
from serge.voice.policy import VoiceBrokerDenied  # noqa: E402

POLICY = {
    'budget': {'llm_daily_eur': 5.0, 'llm_eur_per_1k_tokens': 0.004},
    'quotas': {'llm_recalls_json': 1},
    'observation': {'tech_fail_pattern_per_week': 3},
    'consent': {'opt_in_channels': ['voice', 'sms']},
    'calling_zones': {'default': 'FR', 'FR': {'contact_per_30d': 4}},
}
NOW = '2026-09-09T19:00:00+00:00'


class CallPollTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SMOKE_RUNNING',1,'t','t')"
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, phone,'
            ' regime, funnel_state, created_at, updated_at)'
            " VALUES('p1','v1','Ada','ada@x.io','+33612345678','OUTBOUND',"
            "'CONTACTING','t','t')"
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

    def test_voice_send_ok(self) -> None:
        from serge.workers.call import run_voice_send

        def _ok(**kwargs):
            self.assertEqual(kwargs['to_e164'], '+33612345678')
            self.assertTrue(kwargs['request_id'].startswith('req_'))
            return {
                'decision': 'allowed',
                'cdr_id': 'cdr_1',
                'originated': True,
            }

        result = run_voice_send(
            self.conn,
            POLICY,
            self._item('voice.send', 'k-v1', {'contact_id': 'p1'}),
            originator=_ok,
        )
        self.assertEqual(
            (result['status'], result['cdr_id']), ('done', 'cdr_1')
        )

    def test_voice_send_refus_et_trunk(self) -> None:
        from serge.workers.call import run_voice_send

        denied = run_voice_send(
            self.conn,
            POLICY,
            self._item('voice.send', 'k-v2', {'contact_id': 'p1'}),
            originator=lambda **kw: {
                'decision': 'denied',
                'reason': 'no_consent_or_contract',
            },
        )
        self.assertIn('no_consent', denied['error'])
        trunk = run_voice_send(
            self.conn,
            POLICY,
            self._item('voice.send', 'k-v3', {'contact_id': 'p1'}),
            originator=lambda **kw: {
                'decision': 'allowed',
                'cdr_id': 'c',
                'originated': False,
                'error': 'trunk_down',
            },
        )
        self.assertIn('trunk', trunk['error'])

        def _boom(**kwargs):
            raise VoiceBrokerDenied('bad')

        raised = run_voice_send(
            self.conn,
            POLICY,
            self._item('voice.send', 'k-v4', {'contact_id': 'p1'}),
            originator=_boom,
        )
        self.assertIn('broker', raised['error'])
        nophone = run_voice_send(
            self.conn,
            POLICY,
            self._item('voice.send', 'k-v5', {'contact_id': 'pZZ'}),
            originator=lambda **kw: {},
        )
        self.assertEqual(nophone['error'], 'telephone_inconnu')

    def test_poll_ingere_nouveaux(self) -> None:
        from serge.workers.poll import run_email_poll

        body = base64.urlsafe_b64encode(
            'Bonjour, intéressé !'.encode()
        ).decode()
        message = {
            'id': 'g1',
            'snippet': 'Bonjour...',
            'payload': {
                'headers': [
                    {'name': 'From', 'value': 'Ada <ada@x.io>'},
                    {'name': 'Subject', 'value': 'Re: offre'},
                ],
                'parts': [
                    {
                        'mimeType': 'text/plain',
                        'body': {'data': body},
                    }
                ],
            },
        }
        result = run_email_poll(
            self.conn,
            POLICY,
            self._item('email.poll', 'k-p1', {}),
            searcher=lambda *a, **k: [{'id': 'g1'}],
            getter=lambda *a, **k: dict(message),
        )
        self.assertEqual((result['status'], result['new']), ('done', 1))
        row = self.conn.execute(
            'SELECT contact_id, signal FROM inbound_events'
        ).fetchone()
        self.assertEqual(tuple(row), ('p1', 'REPLIED'))
        again = run_email_poll(
            self.conn,
            POLICY,
            self._item('email.poll', 'k-p2', {}),
            searcher=lambda *a, **k: [{'id': 'g1'}],
            getter=lambda *a, **k: dict(message),
        )
        self.assertEqual((again['new'], again['skipped']), (0, 1))

    def test_poll_erreur_search(self) -> None:
        from serge.workers.poll import run_email_poll

        def _boom(*args, **kwargs):
            raise MailError('NETWORK: down')

        result = run_email_poll(
            self.conn,
            POLICY,
            self._item('email.poll', 'k-p3', {}),
            searcher=_boom,
        )
        self.assertIn('recherche', result['error'])


if __name__ == '__main__':
    unittest.main()
