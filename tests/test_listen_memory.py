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
from serge.db_readers import (  # noqa: E402
    ensure_db_readers,
    execute_memory_capsule,
    readers_du_point,
)
from serge.listen.memory import (  # noqa: E402
    create_cycle,
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

    def test_capsule_inconnue_est_refusee(self) -> None:
        result = execute_memory_capsule(self.conn, 'pas-une-capsule', {})
        self.assertEqual(result['code'], 'capsule_inconnue')

    def test_capsule_retourne_donnees_et_materiel(self) -> None:
        cycle = create_cycle(self.conn, 'guide', 5, 1)
        result = execute_memory_capsule(
            self.conn, 'current_listen_cycle', {'cycle_id': cycle}
        )
        self.assertTrue(result['ok'])
        self.assertEqual(result['data'][0]['id'], cycle)
        self.assertTrue(result['description'])
        self.assertTrue(result['prompt_addition'])

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
            [
                'current_listen_cycle',
                'eligible_poc_candidates',
                'known_business_candidates',
            ],
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
