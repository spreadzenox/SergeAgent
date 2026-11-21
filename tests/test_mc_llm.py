#!/usr/bin/env python3
"""MC : modifier une invocation en base (prompt, niveau, priorité, allumée).

Scénarios :
- le propriétaire modifie une invocation ; une valeur mal écrite est
  refusée et rien ne change ;
- une consigne modifiée est rangée sans ses blancs de fin, et l'ancienne
  est gardée au journal ; la même consigne renvoyée n'écrit rien de plus ;
  une consigne vide ou démesurée est refusée ;
- la fiche de l'invocation propose « Modifier la consigne », avec le texte
  actuel.
"""

from __future__ import annotations

import json
import sqlite3
import unittest

from serge.mc.llm_actions import PROMPT_MAX
from serge.mc.proj_llm import project_llm
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

    def _consignes_au_journal(self) -> list[dict]:
        conn = sqlite3.connect(self.db_path)
        try:
            return [
                json.loads(r[0])
                for r in conn.execute(
                    'SELECT payload_json FROM events WHERE'
                    " type='invocation.prompt' ORDER BY id"
                )
            ]
        finally:
            conn.close()

    def test_la_consigne_se_modifie_et_l_ancienne_est_gardee(self) -> None:
        cookie = self._auth_cookie()

        def poster(consigne: object) -> tuple[int, dict]:
            status, _, body = self._api_post(
                '/owner/api/invocation',
                {'invocation_id': 'redacteur', 'prompt': consigne},
                cookie,
            )
            return status, json.loads(body)

        self.assertEqual(poster('  Écris court.\n\n')[0], 200)
        self.assertEqual(self._ligne()[0], 'Écris court.')
        self.assertEqual(
            self._consignes_au_journal(),
            [{'invocation': 'redacteur', 'avant': 'Écris.'}],
        )
        # La même consigne renvoyée n'ajoute rien au journal.
        self.assertEqual(poster('Écris court.')[0], 200)
        self.assertEqual(len(self._consignes_au_journal()), 1)
        # Vide, ou démesurée : refusée, et la consigne reste.
        for refusee in ('', '   \n', 'x' * (PROMPT_MAX + 1), 12):
            status, reponse = poster(refusee)
            self.assertEqual((status, reponse['code']), (400, 'prompt'))
        self.assertEqual(self._ligne()[0], 'Écris court.')
        self.assertEqual(len(self._consignes_au_journal()), 1)

    def test_la_fiche_propose_de_modifier_la_consigne(self) -> None:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            fiche = project_llm(conn, 'redacteur')
        finally:
            conn.close()
        assert fiche is not None
        cadre = next(
            c for c in fiche['cadres'] if c['titre'].endswith('(prompt)')
        )
        self.assertEqual(cadre['texte'], 'Écris.')
        self.assertEqual(
            [
                (a['libelle'], a['route'], a['charge'], a['saisie']['nom'])
                for a in cadre['actions']
            ],
            [
                (
                    'Modifier la consigne',
                    '/owner/api/invocation',
                    {'invocation_id': 'redacteur'},
                    'prompt',
                )
            ],
        )
        self.assertEqual(cadre['actions'][0]['saisie']['defaut'], 'Écris.')


if __name__ == '__main__':
    unittest.main()
