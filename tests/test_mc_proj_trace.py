#!/usr/bin/env python3
"""Trace d'exécution d'une tâche : fiche + contexte (golden).

La fiche d'une tâche montre aussi ses appels d'outils, dans l'ordre : un
appel refusé avec sa raison, et sous un appel ce que la page a signalé
(un clic qui n'a rien fait, et la réponse du site qui dit pourquoi).
"""

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
from serge.mc.proj_taches import fiche_tache  # noqa: E402
from serge.mc.proj_trace import cadre_appels, project_trace  # noqa: E402
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

    def test_la_fiche_montre_les_appels_d_outils(self) -> None:
        self.assertIsNone(cadre_appels(self.conn, self.task))
        self.conn.execute(
            "INSERT INTO tools(id, titre, capability_id) VALUES('agir',"
            " 'Agir dans le vrai Chrome', 'real_browser_action')"
        )
        for seconde, appel in enumerate(
            (
                {
                    'tool': 'agir',
                    'args': '{"action": "cliquer", "ref": "e154"}',
                    'ok': True,
                    'code': '',
                    'erreurs': [
                        'HTTP 429 : https://api.site.example/inscription?…'
                    ],
                },
                {
                    'tool': 'outil_sans_fiche',
                    'args': '{"text": "Continuer"}',
                    'ok': False,
                    'code': 'echec',
                    'detail': 'plusieurs éléments portent ce texte',
                },
                {'tool': 'agir', 'args': '{}', 'ok': False, 'code': ''},
            )
        ):
            self.conn.execute(
                'INSERT INTO events(actor, type, venture_id, payload_json,'
                " ts) VALUES('invocation:appeler', 'tool.call', '', ?, ?)",
                (
                    json.dumps({'task': self.task, **appel}),
                    f'2026-11-21T15:44:2{seconde}+00:00',
                ),
            )
        # L'appel d'une autre tâche n'y est pas.
        self.conn.execute(
            'INSERT INTO events(actor, type, venture_id, payload_json, ts)'
            " VALUES('invocation:x', 'tool.call', '', ?, ?)",
            (json.dumps({'task': 't_autre', 'tool': 'agir'}), NOW),
        )
        cadre = cadre_appels(self.conn, self.task)
        assert cadre is not None
        self.assertEqual(
            cadre['pre'].split('\n'),
            [
                '15:44:20  Agir dans le vrai Chrome'
                '  {"action": "cliquer", "ref": "e154"}  → fait',
                '          la page : HTTP 429 :'
                ' https://api.site.example/inscription?…',
                '15:44:21  outil_sans_fiche  {"text": "Continuer"}'
                '  → refusé : plusieurs éléments portent ce texte',
                '15:44:22  Agir dans le vrai Chrome  {}  → refusé',
            ],
        )
        self.conn.row_factory = sqlite3.Row
        fiche = fiche_tache(self.conn, self.task)
        assert fiche is not None
        self.assertIn(
            'Ses appels d’outils', [c['titre'] for c in fiche['cadres']]
        )

    def test_trace_inconnue(self) -> None:
        self.assertIsNone(project_trace(self.conn, 'wZZ'))
        self.assertIsNone(project_trace(self.conn, ''))


if __name__ == '__main__':
    unittest.main()
