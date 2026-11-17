#!/usr/bin/env python3
"""Projecteurs P3 analyse : goldens des révisions et des métriques."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_analyse import (  # noqa: E402
    project_diffs,
    project_metriques_tickets,
)

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
                'PLAN_POC',
                'Prix',
                'APPROVED',
                '{}',
                '2026-09-09T10:00:00+00:00',
            ),
            (
                't2',
                'PLAN_POC',
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
                'FYI',
                'Vieux',
                'APPROVED',
                '{}',
                '2026-08-01T10:00:00+00:00',
            ),
            (
                't6',
                'TEST_POC',
                'Un POC à essayer',
                'OPEN',
                '{}',
                '2026-09-10T11:00:00+00:00',
            ),
            (
                't7',
                'CONVERSATION',
                'Un prospect attend',
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
            "UPDATE tickets SET versions_json=? WHERE id='t1'",
            ('[{"n": 1, "note": "v1", "at": "2026-09-09T11:00:00+00:00"}]',),
        )

    def test_diffs_golden(self) -> None:
        self.assertEqual(
            project_diffs(self.conn, POLICY, NOW),
            {
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
            },
        )

    def test_metriques_golden(self) -> None:
        self.assertEqual(
            project_metriques_tickets(self.conn, POLICY, NOW),
            {
                'semaine': {'tickets': 6, 'expirations': 1},
                'backlog': 2,
                'approbation': {
                    'taux_global': 2 / 3,
                    'par_type': {'PLAN_POC': 0.5, 'GUICHET': 1.0},
                },
                'rejets': 1,
                'auto_approbations': 1,
                'bypass': 1,
                'guichet': {'resolus': 1, 'expires': 1},
                'reponse_mediane_s': {'PLAN_POC': 5400, 'GUICHET': 1800},
            },
        )


if __name__ == '__main__':
    unittest.main()
