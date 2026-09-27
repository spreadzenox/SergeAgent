#!/usr/bin/env python3
"""MC : modifier une invocation en base (prompt, niveau, priorité, allumée)."""

from __future__ import annotations

import json
import sqlite3
import unittest

from serge.pipeline_seed import seed_pipeline
from tests.mc_server_case import McServerCase


class McInvocationEditTests(McServerCase):
    def setUp(self) -> None:
        super().setUp()
        conn = sqlite3.connect(self.db_path)
        seed_pipeline(
            conn,
            {
                'schema_version': 1,
                'invocations': [
                    {'id': 'redacteur', 'type': 'llm', 'prompt': 'Écris.'}
                ],
            },
        )
        conn.commit()
        conn.close()

    def _ligne(self) -> tuple:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT prompt, model_tier, queue_id, priority, enabled,'
                ' updated_by'
                " FROM invocations WHERE id='redacteur'"
            ).fetchone()
        finally:
            conn.close()

    def test_owner_modifie_une_invocation(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/invocation',
            {
                'invocation_id': 'redacteur',
                'prompt': 'Prompt MC',
                'model_tier': 'smart',
                'queue_id': 'conversations',
                'priority': 80,
                'enabled': False,
            },
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['ok'])
        self.assertEqual(
            self._ligne(), ('Prompt MC', 'smart', 'conversations', 80, 0, 'mc')
        )

    def test_valeurs_refusees(self) -> None:
        cookie = self._auth_cookie()
        for champ, valeur in (
            ('model_tier', 'gpt-5'),
            ('queue_id', 'express'),
            ('priority', 101),
            ('enabled', 'oui'),
        ):
            status, _, body = self._api_post(
                '/owner/api/invocation',
                {'invocation_id': 'redacteur', champ: valeur},
                cookie,
            )
            self.assertEqual(status, 400, champ)
            self.assertEqual(json.loads(body)['code'], champ)
        status, _, _ = self._api_post(
            '/owner/api/invocation',
            {'invocation_id': 'absente', 'prompt': 'x'},
            cookie,
        )
        self.assertEqual(status, 404)
        self.assertEqual(
            self._ligne(), ('Écris.', 'mid', 'works', 10, 1, 'pipeline.yaml')
        )


if __name__ == '__main__':
    unittest.main()
