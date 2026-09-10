#!/usr/bin/env python3
"""Trace d'exécution : fiche + contexte (golden)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_trace import project_trace  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'


class ProjTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email,'
            " created_at, updated_at) VALUES('p1','v1','Ada','ada@x.io',"
            "'t','t')"
        )
        self.conn.execute(
            'INSERT INTO tickets(id, type, title, state,'
            " created_at, updated_at) VALUES('t1','GUICHET','Captcha',"
            "'OPEN','t','t')"
        )
        payload = json.dumps({'result': {'note': 'Appel propre.'}})
        self.conn.execute(
            'INSERT INTO work_items(id, kind, venture_id, contact_id,'
            ' ticket_id, status, priority, idempotency_key, payload_json,'
            " created_at, updated_at) VALUES('w1','voice.send','v1','p1',"
            "'t1','DONE',0,'k1',?,?,?)",
            (payload, NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('scheduler','work.completed','',?,?)",
            (json.dumps({'id': 'w1'}), NOW),
        )
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('runner','cycle','v1',?,?)",
            (json.dumps({'done': 2}), NOW),
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_trace_complete(self) -> None:
        trace = project_trace(self.conn, 'w1')
        self.assertEqual(trace['item']['kind'], 'voice.send')
        self.assertEqual(trace['note'], 'Appel propre.')
        self.assertEqual(trace['ticket']['titre'], 'Captcha')
        self.assertEqual(trace['contact']['display'], 'Ada')
        kinds = [event['type'] for event in trace['evenements']]
        self.assertIn('work.completed', kinds)
        self.assertIn('cycle', kinds)
        stamps = [event['ts'] for event in trace['evenements']]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_trace_inconnue(self) -> None:
        self.assertIsNone(project_trace(self.conn, 'wZZ'))
        self.assertIsNone(project_trace(self.conn, ''))


if __name__ == '__main__':
    unittest.main()
