#!/usr/bin/env python3
"""Couche 3 : cycle leçons, confiance, expiry, top-k, playbooks."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.memory.lessons import (  # noqa: E402
    add_lesson,
    add_pitfall,
    add_playbook,
    confirm_lesson,
    delete_lesson,
    expire_lessons,
    infirm_lesson,
    set_lesson_status,
    top_lessons,
    update_lesson,
)


class LessonsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_cycle_statuts(self) -> None:
        lesson_id = add_lesson(
            self.conn, 'Relancer J+3.', confidence=0.6, sources=['e1']
        )
        fresh = self.conn.execute(
            'SELECT status, sources_json, confidence FROM lessons WHERE id=?',
            (lesson_id,),
        ).fetchone()
        self.assertEqual(tuple(fresh), ('candidate', '["e1"]', 0.6))
        set_lesson_status(self.conn, lesson_id, 'active')
        row = self.conn.execute(
            'SELECT status, confidence FROM lessons WHERE id=?', (lesson_id,)
        ).fetchone()
        self.assertEqual(tuple(row), ('active', 0.6))
        with self.assertRaises(ValueError):
            set_lesson_status(self.conn, lesson_id, 'nope')
        with self.assertRaises(ValueError):
            set_lesson_status(self.conn, 'l_nope', 'active')

    def test_confirm_infirm_deprecate(self) -> None:
        lesson_id = add_lesson(self.conn, 'X.', confidence=0.5)
        grown = confirm_lesson(self.conn, lesson_id)
        self.assertGreater(grown, 0.5)
        result = infirm_lesson(self.conn, lesson_id, deprecate_after=3)
        self.assertEqual(result['infirm_count'], 1)
        self.assertNotEqual(result['status'], 'deprecated')
        infirm_lesson(self.conn, lesson_id, deprecate_after=3)
        result = infirm_lesson(self.conn, lesson_id, deprecate_after=3)
        self.assertEqual(result['status'], 'deprecated')
        with self.assertRaises(ValueError):
            confirm_lesson(self.conn, 'l_nope')

    def test_expiry(self) -> None:
        expired = add_lesson(
            self.conn, 'Vieux.', expires_at='2026-01-01T00:00:00+00:00'
        )
        fresh = add_lesson(
            self.conn, 'Frais.', expires_at='2999-01-01T00:00:00+00:00'
        )
        done = expire_lessons(self.conn, '2026-09-09T00:00:00+00:00')
        self.assertEqual(done, [expired])
        found = [item['id'] for item in top_lessons(self.conn, k=10)]
        self.assertIn(fresh, found)
        self.assertNotIn(expired, found)

    def test_top_k_ordre(self) -> None:
        add_lesson(self.conn, 'Email artisans J+3.', scope='global')
        venture = add_lesson(self.conn, 'Autre sujet.', scope='venture:v1')
        canal = add_lesson(
            self.conn, 'Email généralités.', scope='canal:email'
        )
        top = top_lessons(
            self.conn, ['email'], venture_id='v1', canal='email', k=3
        )
        self.assertEqual(top[0]['id'], venture)
        self.assertEqual(top[1]['id'], canal)
        dep = add_lesson(self.conn, 'Email périmé.')
        set_lesson_status(self.conn, dep, 'deprecated')
        ids = [item['id'] for item in top_lessons(self.conn, ['email'], k=10)]
        self.assertNotIn(dep, ids)
        ids = [
            item['id']
            for item in top_lessons(
                self.conn, ['email'], k=10, include_deprecated=True
            )
        ]
        self.assertIn(dep, ids)

    def test_playbooks_pitfalls(self) -> None:
        book = add_playbook(
            self.conn, 'Relance', 'après silence', ['J+3', 'J+7']
        )
        pit = add_pitfall(self.conn, 'Appeler lundi 8h.', '2/5 x3')
        self.assertTrue(book.startswith('pb_'))
        self.assertTrue(pit.startswith('pf_'))
        count = self.conn.execute('SELECT COUNT(*) FROM playbooks').fetchone()[
            0
        ]
        self.assertEqual(count, 1)

    def test_curation_update_delete(self) -> None:
        lid = add_lesson(self.conn, 'Leçon initiale', confidence=0.6)
        update_lesson(self.conn, lid, 'Leçon corrigée')
        row = self.conn.execute(
            'SELECT statement FROM lessons WHERE id=?', (lid,)
        ).fetchone()
        self.assertEqual(row[0], 'Leçon corrigée')

        with self.assertRaises(ValueError):
            update_lesson(self.conn, lid, '   ')
        with self.assertRaises(ValueError):
            update_lesson(self.conn, 'les_inconnue', 'Texte')

        delete_lesson(self.conn, lid)
        deleted = self.conn.execute(
            'SELECT 1 FROM lessons WHERE id=?', (lid,)
        ).fetchone()
        self.assertIsNone(deleted)

        with self.assertRaises(ValueError):
            delete_lesson(self.conn, lid)


if __name__ == '__main__':
    unittest.main()
