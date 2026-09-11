#!/usr/bin/env python3
"""Projecteurs P3 analyse : goldens diffs/memory/métriques/digest + endpoint."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_analyse import (  # noqa: E402
    project_diffs,
    project_digest,
    project_memory_items,
    project_metriques_tickets,
)
from tests.mc_server_case import McServerCase  # noqa: E402

NOW = '2026-09-10T12:00:00+00:00'
POLICY = {'tickets': {'digest_hour': 8}, 'windows': {'quiet_hours': [[23, 0]]}}


class ProjAnalyseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        conn = self.conn
        tickets = (
            (
                't1',
                'VETO_AMONT',
                'Prix',
                'APPROVED',
                '{}',
                '2026-09-09T10:00:00+00:00',
            ),
            (
                't2',
                'VETO_AMONT',
                'Remise',
                'REJECTED',
                '{}',
                '2026-09-09T10:00:00+00:00',
            ),
            (
                't3',
                'GUICHET',
                'Captcha',
                'APPROVED',
                '{}',
                '2026-09-10T10:00:00+00:00',
            ),
            (
                't4',
                'GUICHET',
                'Sms',
                'EXPIRED',
                '{}',
                '2026-09-05T10:00:00+00:00',
            ),
            (
                't5',
                'ALERT',
                'Vieux',
                'APPROVED',
                '{}',
                '2026-08-01T10:00:00+00:00',
            ),
            (
                't6',
                'POLICY',
                'Plafond',
                'OPEN',
                '{"diff_avant_apres": "5->7", "justification": "pic",'
                ' "impact": "faible"}',
                '2026-09-10T11:00:00+00:00',
            ),
            (
                't7',
                'MEMORY',
                'Leçons',
                'OPEN',
                '{}',
                '2026-09-10T11:00:00+00:00',
            ),
        )
        for tid, typ, titre, etat, charge, created in tickets:
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
                (tid, typ, titre, etat, charge, created, created),
            )
        events = (
            (
                't1',
                '2026-09-09T10:00:00+00:00',
                'serge',
                'transition.draft',
                '{}',
            ),
            (
                't1',
                '2026-09-09T12:00:00+00:00',
                'owner',
                'transition.approved',
                '{}',
            ),
            (
                't2',
                '2026-09-09T10:00:00+00:00',
                'serge',
                'transition.draft',
                '{}',
            ),
            (
                't2',
                '2026-09-09T11:00:00+00:00',
                'owner',
                'transition.rejected',
                '{}',
            ),
            (
                't3',
                '2026-09-10T10:00:00+00:00',
                'serge',
                'transition.draft',
                '{}',
            ),
            (
                't3',
                '2026-09-10T10:30:00+00:00',
                'serge',
                'transition.approved',
                '{}',
            ),
            (
                't4',
                '2026-09-05T10:00:00+00:00',
                'serge',
                'transition.draft',
                '{}',
            ),
            (
                't4',
                '2026-09-09T10:00:00+00:00',
                'serge',
                'transition.expired',
                '{"default_applied": "rien"}',
            ),
            (
                't5',
                '2026-08-01T10:00:00+00:00',
                'serge',
                'transition.draft',
                '{}',
            ),
            (
                't5',
                '2026-08-02T10:00:00+00:00',
                'owner',
                'transition.approved',
                '{}',
            ),
        )
        for tid, ts, acteur, kind, charge in events:
            conn.execute(
                'INSERT INTO ticket_events(ticket_id, ts, actor, kind,'
                ' payload_json) VALUES(?,?,?,?,?)',
                (tid, ts, acteur, kind, charge),
            )
        conn.execute(
            'INSERT INTO ticket_items(id, ticket_id, kind, label, state,'
            " payload_json) VALUES('i-edit','t7','MEMORY','Vieux','edit',"
            '\'{"label": "Neuf"}\')'
        )
        for num in range(1, 6):
            conn.execute(
                'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
                " VALUES(?,'t7','MEMORY',?,'open')",
                (f'm{num}', f'Leçon {num}'),
            )
        conn.execute(
            'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
            " VALUES('q1','t7','QCM','Option','open')"
        )
        conn.execute(
            "UPDATE tickets SET versions_json=? WHERE id='t1'",
            ('[{"n": 1, "note": "v1", "at": "2026-09-09T11:00:00+00:00"}]',),
        )

    def test_diffs_golden(self) -> None:
        self.assertEqual(
            project_diffs(self.conn, POLICY, NOW),
            {
                'policy': [
                    {
                        'ticket_id': 't6',
                        'titre': 'Plafond',
                        'diff': '5->7',
                        'justification': 'pic',
                        'impact': 'faible',
                    }
                ],
                'versions': [
                    {
                        'ticket_id': 't1',
                        'titre': 'Prix',
                        'versions': [
                            {
                                'n': 1,
                                'note': 'v1',
                                'at': '2026-09-09T11:00:00+00:00',
                            }
                        ],
                    }
                ],
                'items': [
                    {
                        'item_id': 'i-edit',
                        'ticket_id': 't7',
                        'avant': 'Vieux',
                        'apres': 'Neuf',
                    }
                ],
            },
        )

    def test_memory_pagination(self) -> None:
        page1 = project_memory_items(self.conn, 1, 2)
        self.assertEqual(
            (page1['total'], page1['pages'], page1['page'], page1['taille']),
            (6, 3, 1, 2),
        )
        self.assertEqual([i['id'] for i in page1['items']], ['m5', 'm4'])
        page3 = project_memory_items(self.conn, 3, 2)
        self.assertEqual([i['id'] for i in page3['items']], ['m1', 'i-edit'])
        vide = project_memory_items(self.conn, 9, 2)
        self.assertEqual((vide['items'], vide['pages']), ([], 3))
        large = project_memory_items(self.conn, 1, 200)
        self.assertEqual(
            (large['taille'], large['pages'], len(large['items'])),
            (100, 1, 6),
        )

    def test_metriques_golden(self) -> None:
        self.assertEqual(
            project_metriques_tickets(self.conn, POLICY, NOW),
            {
                'semaine': {'tickets': 6, 'expirations': 1},
                'backlog': 2,
                'approbation': {
                    'taux_global': 2 / 3,
                    'par_type': {'VETO_AMONT': 0.5, 'GUICHET': 1.0},
                },
                'rejets': 1,
                'auto_approbations': 1,
                'bypass': 1,
                'guichet': {'resolus': 1, 'expires': 1},
                'reponse_mediane_s': {'VETO_AMONT': 5400, 'GUICHET': 1800},
            },
        )

    def test_digest(self) -> None:
        self.assertEqual(
            project_digest(self.conn, POLICY, NOW),
            {'digest_hour': 8, 'quiet_hours': [[23, 0]]},
        )
        self.assertEqual(
            project_digest(self.conn, {}, NOW),
            {'digest_hour': 8, 'quiet_hours': []},
        )


class MemoryEndpointTests(McServerCase):
    def test_memory_endpoint(self) -> None:
        import sqlite3

        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, created_at,'
                " updated_at) VALUES('t1','MEMORY','L','OPEN','t','t')"
            )
            conn.execute(
                'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
                " VALUES('m1','t1','MEMORY','L1','open'),"
                "('m2','t1','MEMORY','L2','keep')"
            )
            conn.commit()
        finally:
            conn.close()
        status, _, _ = self._request('GET', '/owner/api/memory/items')
        self.assertEqual(status, 401)
        status, headers, _ = self._login()
        self.assertEqual(status, 302)
        cookie = {'Cookie': self._cookie(headers)}
        status, _, _ = self._request(
            'GET', '/owner/api/memory/items?page=0', headers=cookie
        )
        self.assertEqual(status, 400)
        status, _, _ = self._request(
            'GET', '/owner/api/memory/items?size=abc', headers=cookie
        )
        self.assertEqual(status, 400)
        status, _, corps = self._request(
            'GET', '/owner/api/memory/items?page=1&size=1', headers=cookie
        )
        self.assertEqual(status, 200)
        charge = json.loads(corps.decode('utf-8'))
        self.assertEqual(
            (charge['total'], charge['pages'], charge['items'][0]['id']),
            (2, 2, 'm2'),
        )
