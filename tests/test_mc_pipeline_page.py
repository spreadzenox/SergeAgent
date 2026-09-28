#!/usr/bin/env python3
"""MC : la page Pipeline, vue d'ensemble du pipeline tel qu'il est en base.

Scénario : sur une base neuve (le demi-cycle de démonstration), la page
montre les liens, les déclencheurs, les outils, les capacités et ce que
les invocations voient des tables. Julien choisit le modèle du niveau
moyen et réécrit le texte « Qui est Serge » ; l'invocation suivante les
reçoit. Un clic sur un lien ouvre sa fiche.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.run import resolve_model  # noqa: E402
from serge.mc.proj_pipeline import project_pipeline  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402


class ProjectionPipelineTests(unittest.TestCase):
    def test_tout_le_pipeline_de_la_base(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        data = project_pipeline(conn, {}, '')
        liens = {lien['id']: lien for lien in data['liens']}
        self.assertEqual(
            liens['formuler_b_vers_choix']['chemin'],
            'Formuler des business B → Choisir les business à tester',
        )
        self.assertEqual(
            liens['formuler_b_vers_choix']['passage'], 'automatique'
        )
        quand = {d['id']: d['quand'] for d in data['declencheurs']}
        self.assertEqual(quand['lancer_cycle'], 'un bouton de Mission Control')
        self.assertEqual(quand['veille_flux'], 'toutes les 360 minutes')
        outils = {o['id']: o for o in data['outils']}
        self.assertEqual(
            outils['lire_tables_vues']['utilise_par'],
            'toutes les invocations LLM',
        )
        self.assertEqual(
            outils['current_listen_cycle']['utilise_par'], '1 invocation(s)'
        )
        capacites = {c['id']: c for c in data['capacites']}
        self.assertTrue(capacites['seen_table_read']['disponible'])
        tables = {t['table']: t for t in data['tables']}
        self.assertEqual(tables['ventures']['courte'], 'id, name')
        self.assertEqual(
            [m['tier'] for m in data['modeles']], ['fast', 'mid', 'smart']
        )
        self.assertIn('opérateur économique autonome', data['presentation'])


class PipelinePageTests(McBrowserCase):
    def _base(self, sql: str) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_regler_le_modele_et_le_texte(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/pipeline')
        section = page.locator('[data-section="pipeline"]')
        for texte in (
            'Les idées passent au choix',
            'Lancer un cycle d’écoute'.replace('’', "'"),
            'Lire les tables que je vois',
            'Lire l’historique d’une ligne',
            'id, name',
        ):
            expect(section).to_contain_text(texte, timeout=10000)
        champ = page.locator('[data-tier="mid"]')
        champ.fill('openai/gpt-5-mini')
        bouton = champ.locator('xpath=../..').get_by_role(
            'button', name='Enregistrer'
        )
        with page.expect_response('**/owner/api/pipeline/modele') as reponse:
            bouton.click()
        self.assertTrue(reponse.value.ok)
        conn = sqlite3.connect(self.db_path)
        try:
            self.assertEqual(
                resolve_model(conn, 'mid')[0], 'openai/gpt-5-mini'
            )
        finally:
            conn.close()
        page.locator('[data-pipeline="texte"]').fill(
            'Serge, version de Julien.'
        )
        with page.expect_response('**/owner/api/pipeline/texte') as reponse:
            page.get_by_role('button', name='Enregistrer le texte').click()
        self.assertTrue(reponse.value.ok)
        self.assertEqual(
            self._base("SELECT body FROM serge_texts WHERE id='presentation'"),
            [('Serge, version de Julien.',)],
        )
        page.locator(
            '[data-pipeline="liens"] tr', has_text='Les idées passent au choix'
        ).click()
        expect(page.locator('#page')).to_contain_text('Ce qui attend un clic')

    def test_valeurs_refusees(self) -> None:
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/pipeline/modele',
            {'tier': 'mid', 'model': 'rm -rf /; x'},
            cookie,
        )
        self.assertEqual(status, 400)
        status, _, _ = self._api_post(
            '/owner/api/pipeline/modele',
            {'tier': 'ultra', 'model': 'x'},
            cookie,
        )
        self.assertEqual(status, 409)
        status, _, _ = self._api_post(
            '/owner/api/pipeline/texte', {'body': '   '}, cookie
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            self._base("SELECT model FROM llm_models WHERE tier='mid'"),
            [('',)],
        )


if __name__ == '__main__':
    unittest.main()
