#!/usr/bin/env python3
"""Projecteurs P4 Mémoire : goldens C1-C5, consolidation, requested + search."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import open_db  # noqa: E402
from serge.mc.proj_memory import (  # noqa: E402
    project_consolidation,
    project_couches,
    project_requested,
)
from serge.memory.search import index_document  # noqa: E402
from serge.memory.summaries import put_summary  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY: dict = {'memory': {'consolidation_days': 3}}


class ProjMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn

        # C1
        conn.execute(
            'INSERT INTO episode_archives(id, path, period, count, sha256,'
            ' created_at) VALUES(1, "/tmp/ep1.tar", "2026-08", 42, "abcd1234ef5678",'
            ' "2026-09-01T10:00:00+00:00")'
        )

        # C2
        conn.execute(
            'INSERT INTO playbooks(id, name, conditions, steps_json, scope,'
            ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'pb1',
                'Relance Named',
                'apres 3j sans reponse',
                '["email", "sms"]',
                'global',
                '2026-09-02T10:00:00+00:00',
                '2026-09-02T10:00:00+00:00',
            ),
        )

        # C3
        conn.execute(
            'INSERT INTO pitfalls(id, statement, cost_observed, scope,'
            ' created_at) VALUES(?,?,?,?,?)',
            (
                'pf1',
                'Ne jamais promettre de remise directe',
                'perte de marge',
                'global',
                '2026-09-03T10:00:00+00:00',
            ),
        )

        # C4
        conn.execute(
            'INSERT INTO lessons(id, statement, confidence, scope, status,'
            ' confirm_count, infirm_count, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?,?)',
            (
                'les1',
                'Toujours valider le SIRET',
                0.85,
                'global',
                'active',
                5,
                1,
                '2026-09-04T10:00:00+00:00',
                '2026-09-04T10:00:00+00:00',
            ),
        )

        # C5
        put_summary(conn, 'serge_md', '# Serge\nAgent commercial autonome.')
        put_summary(conn, 'serge_md', '# Serge\nAgent commercial autonome v2.')

        # Consolidation summary & events
        put_summary(conn, 'consolidation', '2026-09-08T10:00:00+00:00')
        conn.execute(
            'INSERT INTO events(ts, actor, type, payload_json) VALUES(?,?,?,?)',
            (
                '2026-09-08T10:00:00+00:00',
                'consolidate',
                'consolidate.run',
                '{"lessons_added": 2}',
            ),
        )

        # Requested tickets
        conn.execute(
            'INSERT INTO tickets(id, type, title, state, payload_json,'
            ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'req1',
                'REQUESTED',
                'Ajout filtre secteur',
                'OPEN',
                '{"demande": "Permettre le filtre par code NAF", "contexte": "prospection B2B", "point_llm": "qualify"}',
                '2026-09-09T10:00:00+00:00',
                '2026-09-09T10:00:00+00:00',
            ),
        )

    def test_couches_golden(self) -> None:
        data = project_couches(self.conn, POLICY, NOW)
        c1 = data['c1']
        self.assertEqual(c1['total_archives'], 1)
        self.assertEqual(c1['total_episodes'], 42)
        self.assertEqual(c1['archives'][0]['period'], '2026-08')

        c2 = data['c2']
        self.assertEqual(c2['total'], 1)
        self.assertEqual(c2['items'][0]['nom'], 'Relance Named')

        c3 = data['c3']
        self.assertEqual(c3['total'], 1)
        self.assertIn('remise directe', c3['items'][0]['piege'])

        c4 = data['c4']
        self.assertEqual(c4['total'], 1)
        self.assertEqual(c4['items'][0]['confiance'], 0.85)
        self.assertEqual(c4['items'][0]['confirmations'], 5)

        c5 = data['c5']
        self.assertEqual(c5['version'], 2)
        self.assertIn('v2', c5['content'])
        self.assertIn('autonome.', c5['previous'])

    def test_consolidation_golden(self) -> None:
        data = project_consolidation(self.conn, POLICY, NOW)
        self.assertEqual(data['last_run'], '2026-09-08T10:00:00+00:00')
        self.assertFalse(data['due'])  # 2 jours écoulés vs 3j
        self.assertEqual(len(data['events']), 1)
        self.assertEqual(data['events'][0]['acteur'], 'consolidate')

    def test_requested_golden(self) -> None:
        data = project_requested(self.conn, POLICY, NOW)
        self.assertEqual(len(data['items']), 1)
        req = data['items'][0]
        self.assertEqual(req['id'], 'req1')
        self.assertEqual(req['point_llm'], 'qualify')
        self.assertIn('code NAF', req['demande'])


class MemorySearchEndpointTests(McServerCase):
    def test_search_endpoint(self) -> None:
        conn = open_db(self.db_path)
        try:
            index_document(
                conn, 'lesson', 'les_42', 'Leçon sur les remises tarifaires'
            )
            conn.commit()
        finally:
            conn.close()

        status, _, _ = self._request('GET', '/owner/api/memory/search')
        self.assertEqual(status, 401)

        cookie = self._auth_cookie()
        status, _, _ = self._request(
            'GET', '/owner/api/memory/search', headers={'Cookie': cookie}
        )
        self.assertEqual(status, 400)

        status, _, corps = self._request(
            'GET',
            '/owner/api/memory/search?q=remises',
            headers={'Cookie': cookie},
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertIn('results', data)
        self.assertTrue(len(data['results']) >= 1)
        self.assertEqual(data['results'][0]['id'], 'les_42')
