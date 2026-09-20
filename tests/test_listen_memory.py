#!/usr/bin/env python3
"""Contrats mémoire et permissions de l'objectif écoute."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db_readers import ensure_db_readers, readers_du_point  # noqa: E402
from serge.listen.memory import (  # noqa: E402
    create_cycle,
    current_cycle,
    read_named,
    save_candidates,
    select_poc,
)


class ListenMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO listen_docs(id, source, title, excerpt, fetched_at) '
            "VALUES('d1','forum','Besoin','Une douleur','2026-09-16T00:00:00Z')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_cycle_ne_reprend_pas_un_document_deja_explore(self) -> None:
        first = create_cycle(self.conn, '', 5, 1)
        self.assertEqual(
            self.conn.execute(
                'SELECT COUNT(*) FROM listen_cycle_docs WHERE cycle_id=?',
                (first,),
            ).fetchone()[0],
            1,
        )

    def test_lecteur_cycle_utilise_les_noms_de_parametres_policy(self) -> None:
        cycle = create_cycle(self.conn, 'guide', 5, 1)
        result = current_cycle(self.conn, cycle)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result['id'], cycle)
        self.assertEqual(result['guide'], 'guide')
        self.assertEqual(result['needs_target'], 5)
        self.assertEqual(result['business_target'], 1)
        self.assertEqual(result['status'], 'READY')
        second = create_cycle(self.conn, '', 5, 1)
        self.assertEqual(
            self.conn.execute(
                'SELECT COUNT(*) FROM listen_cycle_docs WHERE cycle_id=?',
                (second,),
            ).fetchone()[0],
            0,
        )

    def test_lecteur_refuse_hors_permission(self) -> None:
        result = read_named(
            self.conn,
            'listen_discover_needs_a',
            'eligible_poc_candidates',
            {},
        )
        self.assertEqual(result['code'], 'permission_refusee')

    def test_permissions_sont_reprojetees_depuis_le_registre(self) -> None:
        self.conn.execute(
            'INSERT INTO llm_point_readers'
            '(point_id, reader_id, usage, enabled) '
            "VALUES('listen_choose_poc', 'known_business_candidates', 'autorise', 1)"
        )
        ensure_db_readers(self.conn)
        self.assertEqual(
            [
                item['id']
                for item in readers_du_point(
                    self.conn, 'listen_discover_needs_a'
                )
            ],
            [
                'current_listen_cycle',
                'known_business_candidates',
                'listen_cycle_documents',
            ],
        )
        self.assertEqual(
            [
                item['id']
                for item in readers_du_point(self.conn, 'listen_choose_poc')
            ],
            ['current_listen_cycle', 'eligible_poc_candidates'],
        )

    def test_candidat_poc_est_verrouille(self) -> None:
        cycle = create_cycle(self.conn, '', 5, 1)
        self.assertEqual(
            save_candidates(
                self.conn,
                cycle,
                {
                    'needs': [
                        {
                            'title': 'Besoin A',
                            'content': 'Détail A',
                            'evidence_ids': ['d1'],
                        }
                    ]
                },
            ),
            1,
        )
        candidate = self.conn.execute(
            'SELECT id FROM business_candidates'
        ).fetchone()[0]
        selected = select_poc(
            self.conn, cycle, {'candidate_ids': [candidate]}, 1
        )
        self.assertEqual(selected, [candidate])
        self.assertEqual(
            select_poc(self.conn, cycle, {'candidate_ids': [candidate]}, 1), []
        )


if __name__ == '__main__':
    unittest.main()
