#!/usr/bin/env python3
"""Édition MC des métadonnées runtime LLM."""

from __future__ import annotations

import json
import sqlite3

from tests.mc_server_case import McServerCase


class McLlmMetadataTests(McServerCase):
    def test_owner_edite_un_point_en_base(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/llm-point',
            {
                'point_id': 'classify_reply',
                'prompt': 'Prompt MC',
                'output_mode': 'text',
                'external_info': True,
            },
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['ok'])
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(
                conn.execute(
                    'SELECT prompt, output_mode, external_info FROM llm_points'
                    " WHERE id='classify_reply'"
                ).fetchone(),
                ('Prompt MC', 'text', 1),
            )
        finally:
            conn.close()


if __name__ == '__main__':
    import unittest

    unittest.main()
