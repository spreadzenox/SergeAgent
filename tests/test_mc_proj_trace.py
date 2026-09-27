#!/usr/bin/env python3
"""Trace d'exécution d'une tâche : fiche + contexte (golden)."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_trace import project_trace  # noqa: E402
from tests.taches_fixtures import invocations, tache  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'


class ProjTraceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, created_at, updated_at) VALUES(?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                't',
                't',
            ),
        )
        add_address(self.conn, 'p1', 'email', 'ada@x.io')
        invocations(self.conn, ('appeler', 'Appeler', 'prospection_lourde'))
        self.task = tache(
            self.conn,
            'appeler',
            {'venture_id': 'v1', 'contact_id': 'p1'},
            key='k1',
            status='failed',
            error='ligne occupée',
        )
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('invocation:appeler','task.failed','',?,?)",
            (json.dumps({'task': self.task}), NOW),
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
        trace = project_trace(self.conn, self.task)
        self.assertEqual(trace['item']['kind'], 'Appeler')
        self.assertEqual(trace['item']['statut'], 'failed')
        self.assertEqual(trace['note'], 'ligne occupée')
        self.assertIsNone(trace['ticket'])
        self.assertEqual(trace['contact']['display'], 'Ada')
        kinds = [event['type'] for event in trace['evenements']]
        self.assertIn('task.failed', kinds)
        self.assertIn('cycle', kinds)
        stamps = [event['ts'] for event in trace['evenements']]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_trace_inconnue(self) -> None:
        self.assertIsNone(project_trace(self.conn, 'wZZ'))
        self.assertIsNone(project_trace(self.conn, ''))


if __name__ == '__main__':
    unittest.main()
