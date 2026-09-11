#!/usr/bin/env python3
"""MC actes mémoire : curation leçons + rollback SERGE.md + audit."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.memory.lessons import add_lesson  # noqa: E402
from serge.memory.summaries import get_summary, put_summary  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class MemoryActesTests(McServerCase):
    def test_lesson_modifier_et_supprimer(self) -> None:
        conn = open_db(self.db_path)
        try:
            lid = add_lesson(
                conn, 'Toujours vérifier les prix', confidence=0.7
            )
            conn.commit()
        finally:
            conn.close()

        # Sans auth -> 401
        status, _, _ = self._api_post(
            '/owner/api/memory/lesson',
            {
                'lesson_id': lid,
                'action': 'modifier',
                'statement': 'Texte revu',
            },
        )
        self.assertEqual(status, 401)

        cookie = self._auth_cookie()

        # Erreurs de validation -> 400
        for charge in (
            {'lesson_id': '', 'action': 'modifier', 'statement': 'x'},
            {'lesson_id': lid, 'action': 'inconnue'},
            {'lesson_id': lid, 'action': 'modifier', 'statement': '   '},
            '{pas json',
        ):
            with self.subTest(charge=charge):
                status, _, _ = self._api_post(
                    '/owner/api/memory/lesson', charge, cookie
                )
                self.assertEqual(status, 400)

        # Leçon inconnue -> 404
        status, _, _ = self._api_post(
            '/owner/api/memory/lesson',
            {
                'lesson_id': 'les_inconnue',
                'action': 'modifier',
                'statement': 'x',
            },
            cookie,
        )
        self.assertEqual(status, 404)

        # Modification valide -> 200 + audit
        status, _, corps = self._api_post(
            '/owner/api/memory/lesson',
            {
                'lesson_id': lid,
                'action': 'modifier',
                'statement': 'Toujours vérifier les devis et prix',
                'decision_id': 'dec_mod_1',
            },
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertEqual(data['action'], 'modifier')

        conn = open_db(self.db_path)
        try:
            row = conn.execute(
                'SELECT statement FROM lessons WHERE id=?', (lid,)
            ).fetchone()
            self.assertEqual(row[0], 'Toujours vérifier les devis et prix')

            ev = conn.execute(
                "SELECT payload_json FROM events WHERE type='mc_act'"
                ' ORDER BY id DESC LIMIT 1'
            ).fetchone()
            ev_data = json.loads(ev[0])
            self.assertEqual(ev_data['acte'], 'curation_lesson')
            self.assertEqual(ev_data['action'], 'modifier')
            self.assertEqual(ev_data['decision_id'], 'dec_mod_1')
        finally:
            conn.close()

        # Suppression valide -> 200 + audit
        status, _, corps = self._api_post(
            '/owner/api/memory/lesson',
            {
                'lesson_id': lid,
                'action': 'supprimer',
                'decision_id': 'dec_sup_1',
            },
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertEqual(data['action'], 'supprimer')

        conn = open_db(self.db_path)
        try:
            row = conn.execute(
                'SELECT 1 FROM lessons WHERE id=?', (lid,)
            ).fetchone()
            self.assertIsNone(row)
        finally:
            conn.close()

    def test_rollback_serge_md(self) -> None:
        conn = open_db(self.db_path)
        try:
            put_summary(conn, 'serge_md', 'Version 1 de Serge.')
            put_summary(conn, 'serge_md', 'Version 2 de Serge modifiée.')
            conn.commit()
        finally:
            conn.close()

        # Sans auth -> 401
        status, _, _ = self._api_post('/owner/api/memory/rollback', {})
        self.assertEqual(status, 401)

        cookie = self._auth_cookie()

        # Rollback valide -> 200 + audit
        status, _, corps = self._api_post(
            '/owner/api/memory/rollback',
            {'decision_id': 'dec_roll_1'},
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertTrue(data['ok'])
        self.assertTrue(data['restaure'])

        conn = open_db(self.db_path)
        try:
            summary = get_summary(conn, 'serge_md')
            self.assertIsNotNone(summary)
            self.assertEqual(summary['content'], 'Version 1 de Serge.')
            self.assertEqual(summary['version'], 3)

            ev = conn.execute(
                "SELECT payload_json FROM events WHERE type='mc_act'"
                ' ORDER BY id DESC LIMIT 1'
            ).fetchone()
            ev_data = json.loads(ev[0])
            self.assertEqual(ev_data['acte'], 'rollback_serge_md')
            self.assertEqual(ev_data['decision_id'], 'dec_roll_1')
        finally:
            conn.close()

        # Deuxième rollback -> réapplique l'ancienne (car previous redevient Version 2)
        status, _, _ = self._api_post(
            '/owner/api/memory/rollback',
            {'decision_id': 'dec_roll_2'},
            cookie,
        )
        self.assertEqual(status, 200)


if __name__ == '__main__':
    unittest.main()
