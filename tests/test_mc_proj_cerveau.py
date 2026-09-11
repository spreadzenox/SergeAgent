#!/usr/bin/env python3
"""Projecteurs P2 : goldens signaux/clusters/décisions/pensées/usage."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_cerveau import (  # noqa: E402
    project_clusters,
    project_decisions,
    project_matrice,
    project_pensees,
    project_signaux,
    project_usage_points,
)

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
            'INSERT INTO inbound_events(id, contact_id, channel, native_type,'
            " signal, class, score, received_at) VALUES('b1','p1','sms',"
            "'MO','reply','positive',0.9,'2026-09-10T11:20:00+00:00')"
        )
        conn.execute(
            'INSERT INTO inbound_events(id, contact_id, channel, native_type,'
            " signal, class, score, received_at) VALUES('b2','p2','email',"
            "'reply','bounce','',0,'2026-09-10T11:10:00+00:00')"
        )
        for did, cluster, fetched in (
            ('d1', 'cA', '2026-09-10T11:00:00+00:00'),
            ('d2', 'cA', '2026-09-10T11:30:00+00:00'),
            ('d3', 'cB', '2026-09-08T11:00:00+00:00'),
            ('d4', '', '2026-09-10T11:00:00+00:00'),
        ):
            conn.execute(
                'INSERT INTO listen_docs(id, source, cluster_id, fetched_at)'
                " VALUES(?,'rss',?,?)",
                (did, cluster, fetched),
            )

    def test_signaux_golden(self) -> None:
        self.assertEqual(
            project_signaux(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'channel': 'sms',
                        'type': 'MO',
                        'signal': 'reply',
                        'classe': 'positive',
                        'score': 0.9,
                        'contact_id': 'p1',
                        'ts': '2026-09-10T11:20:00+00:00',
                    },
                    {
                        'channel': 'email',
                        'type': 'reply',
                        'signal': 'bounce',
                        'classe': '',
                        'score': 0.0,
                        'contact_id': 'p2',
                        'ts': '2026-09-10T11:10:00+00:00',
                    },
                ]
            },
        )

    def test_clusters_golden(self) -> None:
        self.assertEqual(
            project_clusters(self.conn, POLICY, NOW),
            {
                'items': [
                    {
                        'id': 'cA',
                        'docs': 2,
                        'dernier': '2026-09-10T11:30:00+00:00',
                    }
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


REGISTRE_DEMO = """schema_version: 1
points:
  qualify:
    verdict: LLM-1
    tier: T1
    checklist: {entree: true}
    context: {fixed: [], retrieved: [], couche5: {allowed: false},
      forbidden: [], envelope_tokens: 2500}
    garde_fou: strict
    repli: manuel
    enabled: true
  score:
    verdict: LLM-1
    tier: T1
    checklist: {entree: true}
    context: {fixed: [], retrieved: [], couche5: {allowed: false},
      forbidden: [], envelope_tokens: 1000}
    garde_fou: strict
    repli: manuel
    enabled: false
"""


class ProjMatriceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix='serge-matrice-')
        self.addCleanup(self.tmp.cleanup)
        self.reg_path = Path(self.tmp.name) / 'llm-points.yaml'
        self.reg_path.write_text(REGISTRE_DEMO, encoding='utf-8')
        patcher = mock.patch.dict(
            os.environ, {'SERGE_CONFIG_DIR': self.tmp.name}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        _insere_usage(self.conn)
        for jour in ('2026-09-09', '2026-09-07', '2026-09-06'):
            self.conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('qualify','T1','nemo',100,50,10,'ok',?)",
                (f'{jour}T10:00:00+00:00',),
            )
        for jour in (
            '2026-09-08',
            '2026-09-07',
            '2026-09-06',
            '2026-09-05',
        ):
            self.conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('score','T1','nemo',100,50,10,'ok',?)",
                (f'{jour}T10:00:00+00:00',),
            )
        for heure in ('10', '11', '14', '15'):
            self.conn.execute(
                'INSERT INTO llm_usage(point, tier, model, tokens_in,'
                ' tokens_out, latency_ms, verdict, created_at)'
                " VALUES('score','T1','nemo',100,50,10,'ok',?)",
                (f'2026-09-09T{heure}:00:00+00:00',),
            )

    def test_matrice_golden(self) -> None:
        self.assertEqual(
            project_matrice(self.conn, POLICY, NOW),
            {
                'points': [
                    {
                        'nom': 'qualify',
                        'tier': 'T1',
                        'verdict': 'LLM-1',
                        'enabled': True,
                        'checklist': {'entree': True},
                        'garde_fou': 'strict',
                        'repli': 'manuel',
                        'enveloppe': 2500,
                        'appels_7j': 3,
                        'tokens_7j': 450,
                        'latence_ms': 10,
                        'verdicts': {'ok': 3},
                        'derive': '',
                    },
                    {
                        'nom': 'score',
                        'tier': 'T1',
                        'verdict': 'LLM-1',
                        'enabled': False,
                        'checklist': {'entree': True},
                        'garde_fou': 'strict',
                        'repli': 'manuel',
                        'enveloppe': 1000,
                        'appels_7j': 8,
                        'tokens_7j': 1200,
                        'latence_ms': 10,
                        'verdicts': {'ok': 8},
                        'derive': 'volume',
                    },
                ]
            },
        )

    def test_matrice_registre_absent(self) -> None:
        self.reg_path.unlink()
        self.assertEqual(
            project_matrice(self.conn, POLICY, NOW),
            {'points': [], 'erreur': 'registre illisible'},
        )
