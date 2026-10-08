#!/usr/bin/env python3
"""Projecteurs P2 : goldens signaux/clusters/décisions/pensées/usage."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_cerveau import (  # noqa: E402
    project_decisions,
    project_matrice,
    project_pensees,
    project_signaux,
    project_usage_points,
)
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {}


def _insere_usage(conn: sqlite3.Connection) -> None:
    for point, tier, model, tin, tout, lat, verdict, created in (
        (
            'qualify',
            'T1',
            'nemo',
            1000,
            500,
            100,
            'ok',
            '2026-09-10T11:00:00+00:00',
        ),
        (
            'qualify',
            'T1',
            'nemo',
            2000,
            1000,
            200,
            'recall',
            '2026-09-10T11:30:00+00:00',
        ),
        (
            'score',
            'T1',
            'nemo',
            500,
            100,
            50,
            'ok',
            '2026-09-10T11:45:00+00:00',
        ),
        (
            'qualify',
            'T1',
            'nemo',
            500,
            250,
            75,
            'ok',
            '2026-09-01T12:00:00+00:00',
        ),
    ):
        conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            ' tokens_out, latency_ms, verdict, created_at)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (point, tier, model, tin, tout, lat, verdict, created),
        )


class ProjCerveauTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn
        _insere_usage(conn)
        conn.execute(
            'INSERT INTO contacts(id, venture_id, display, created_at,'
            " updated_at) VALUES('p1','v1','Ada','t','t')"
        )
        conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel, status,'
            " reaction, received_at) VALUES('b1','p1','email','attached',"
            "'question','2026-09-10T11:20:00+00:00')"
        )
        conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel, address,'
            " status, received_at) VALUES('b2','','email','x@example.org',"
            "'unattached','2026-09-10T11:10:00+00:00')"
        )
        for did, cluster, fetched, titre in (
            ('d1', 'cA', '2026-09-10T11:00:00+00:00', 'Bruit prix'),
            ('d2', 'cA', '2026-09-10T11:30:00+00:00', 'Bug synchro'),
            ('d3', 'cB', '2026-09-08T11:00:00+00:00', 'Vieux sujet'),
            ('d4', '', '2026-09-10T11:00:00+00:00', 'Orphelin'),
        ):
            conn.execute(
                'INSERT INTO listen_docs(id, source, cycle_id, fetched_at,'
                " title) VALUES(?,'rss',?,?,?)",
                (did, cluster, fetched, titre),
            )

    def test_signaux_golden(self) -> None:
        self.assertEqual(
            project_signaux(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'channel': 'email',
                        'reaction': 'question',
                        'rattache': True,
                        'contact': 'Ada',
                        'contact_id': 'p1',
                        'ts': '2026-09-10T11:20:00+00:00',
                    },
                    {
                        'channel': 'email',
                        'reaction': '',
                        'rattache': False,
                        'contact': 'x@example.org',
                        'contact_id': '',
                        'ts': '2026-09-10T11:10:00+00:00',
                    },
                ]
            },
        )

    def test_decisions_golden(self) -> None:
        projete = project_decisions(self.conn, POLICY, NOW)['items']
        self.assertEqual(
            [(d['point'], d['tokens'], d['verdict']) for d in projete],
            [
                ('score', 600, 'ok'),
                ('qualify', 3000, 'recall'),
                ('qualify', 1500, 'ok'),
                ('qualify', 750, 'ok'),
            ],
        )
        self.assertEqual(projete[0]['latence_ms'], 50)
        self.assertEqual(projete[0]['tier'], 'T1')

    def test_pensees_stub(self) -> None:
        self.assertEqual(
            project_pensees(self.conn, POLICY, NOW),
            {'items': [], 'source': 'aucune (émetteurs futurs)'},
        )

    def test_usage_points_golden(self) -> None:
        self.assertEqual(
            project_usage_points(self.conn, POLICY, NOW),
            {
                'points': [
                    {
                        'point': 'qualify',
                        'appels': 2,
                        'tokens': 4500,
                        'latence_ms': 150.0,
                        'verdicts': {'ok': 1, 'recall': 1},
                    },
                    {
                        'point': 'score',
                        'appels': 1,
                        'tokens': 600,
                        'latence_ms': 50.0,
                        'verdicts': {'ok': 1},
                    },
                ]
            },
        )


class ProjMatriceTests(unittest.TestCase):
    """La liste des invocations en base, avec leur usage sur 7 jours."""

    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        sans_pipeline_de_depart(self.conn)
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {
                        'id': 'score',
                        'title': 'Noter',
                        'type': 'llm',
                        'model_tier': 'fast',
                        'step': 'prospection_lourde',
                        'queue': 'conversations',
                        'enabled': False,
                    },
                    {
                        'id': 'qualify',
                        'title': 'Qualifier',
                        'type': 'llm',
                        'step': 'prospection_light',
                        'priority': 50,
                    },
                ],
            },
        )
        _insere_usage(self.conn)
        for jour in ('2026-09-09', '2026-09-07', '2026-09-06'):
            self.conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('qualify','mid','nemo',100,50,10,'ok',?)",
                (f'{jour}T10:00:00+00:00',),
            )
        for jour in ('2026-09-08', '2026-09-07', '2026-09-06', '2026-09-05'):
            for heure in ('10', '11'):
                self.conn.execute(
                    'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                    ' tokens_out, latency_ms, verdict, created_at)'
                    " VALUES('score','fast','nemo',100,50,10,'ok',?)",
                    (f'{jour}T{heure}:00:00+00:00',),
                )

    def test_matrice_golden(self) -> None:
        self.assertEqual(
            project_matrice(self.conn, POLICY, NOW),
            {
                'points': [
                    {
                        'nom': 'qualify',
                        'titre': 'Qualifier',
                        'tier': 'mid',
                        'type': 'llm',
                        'enabled': True,
                        'file': 'works',
                        'priorite': 50,
                        'etape': 'prospection_light',
                        'appels_7j': 5,
                        'tokens_7j': 4950,
                        'latence_ms': 66,
                        'verdicts': {'ok': 4, 'recall': 1},
                    },
                    {
                        'nom': 'score',
                        'titre': 'Noter',
                        'tier': 'fast',
                        'type': 'llm',
                        'enabled': False,
                        'file': 'conversations',
                        'priorite': 10,
                        'etape': 'prospection_lourde',
                        'appels_7j': 9,
                        'tokens_7j': 1800,
                        'latence_ms': 14,
                        'verdicts': {'ok': 9},
                    },
                ]
            },
        )

    def test_une_invocation_supprimee_disparait(self) -> None:
        self.conn.execute(
            "UPDATE invocations SET deleted_at=? WHERE id='score'", (NOW,)
        )
        points = project_matrice(self.conn, POLICY, NOW)['points']
        self.assertEqual([p['nom'] for p in points], ['qualify'])


if __name__ == '__main__':
    unittest.main()
