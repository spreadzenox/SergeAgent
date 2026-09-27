#!/usr/bin/env python3
"""MC Écoute : le bouton lance l'invocation de son déclencheur, lu en base.

Scénario : un déclencheur « bouton » de l'étape 1 lance « Ouvrir un
cycle » avec le texte de guidage du formulaire. Cliquer dans Mission
Control crée la tâche, avec ce texte en paramètre. Sans déclencheur en
base, le bouton est grisé et la page le dit.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.proj_ecoute import project_ecoute  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.mc_server_case import McBrowserCase, McServerCase  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402

PIPELINE = {
    'schema_version': 1,
    'invocations': [
        {
            'id': 'ouvrir_cycle',
            'title': 'Ouvrir un cycle',
            'type': 'capability',
            'capability': 'echo',
            'step': 'pre_prospection',
        }
    ],
    'triggers': [
        {
            'id': 'bouton_cycle',
            'title': 'Lancer un cycle d’écoute',
            'invocation': 'ouvrir_cycle',
            'event': 'button',
            'params': {'guide': {'source': 'form', 'value': 'guide'}},
        }
    ],
}


def _seed(db_path: Path, pipeline: dict | None = PIPELINE) -> None:
    conn = sqlite3.connect(db_path)
    sans_pipeline_de_depart(conn)
    if pipeline:
        seed_pipeline(conn, pipeline)
    conn.commit()
    conn.close()


def _guides(db_path: Path) -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [
            str(r[0])
            for r in conn.execute(
                'SELECT p.value FROM tasks t JOIN task_params p'
                " ON p.task_id=t.id AND p.name='guide'"
                " WHERE t.invocation_id='ouvrir_cycle'"
            ).fetchall()
        ]
    finally:
        conn.close()


class McBoutonApiTests(McServerCase):
    def test_le_bouton_cree_la_tache(self) -> None:
        _seed(self.db_path)
        cookie = self._auth_cookie()
        status, _, body = self._api_post(
            '/owner/api/bouton',
            {'trigger_id': 'bouton_cycle', 'form': {'guide': 'artisans'}},
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)['task_id'])
        self.assertEqual(_guides(self.db_path), ['artisans'])

    def test_bouton_inconnu_ou_sans_auth(self) -> None:
        _seed(self.db_path)
        status, _, _ = self._api_post(
            '/owner/api/bouton', {'trigger_id': 'bouton_cycle'}
        )
        self.assertEqual(status, 401)
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/bouton', {'trigger_id': 'absent'}, cookie
        )
        self.assertEqual(status, 409)
        self.assertEqual(_guides(self.db_path), [])

    def test_projection(self) -> None:
        _seed(self.db_path)
        conn = sqlite3.connect(self.db_path)
        try:
            data = project_ecoute(conn, {}, '')
        finally:
            conn.close()
        self.assertEqual(
            data['boutons'],
            [
                {
                    'id': 'bouton_cycle',
                    'titre': 'Lancer un cycle d’écoute',
                    'invocation': 'ouvrir_cycle',
                    'invocation_titre': 'Ouvrir un cycle',
                    'champs': ['guide'],
                }
            ],
        )
        self.assertEqual(
            data['invocations'],
            [{'id': 'ouvrir_cycle', 'titre': 'Ouvrir un cycle'}],
        )


class McEcouteFrontTests(McBrowserCase):
    def test_lancer_depuis_la_page(self) -> None:
        from playwright.sync_api import expect

        _seed(self.db_path)
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/ecoute')
        bouton = page.locator('[data-ecoute-action="lancer"]')
        expect(bouton).to_have_text('Lancer un cycle d’écoute', timeout=10000)
        page.locator('[data-ecoute="guide"]').fill('devis artisans')
        bouton.click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Tâche placée dans la file.'
        )
        self.assertEqual(_guides(self.db_path), ['devis artisans'])

    def test_sans_bouton_en_base(self) -> None:
        from playwright.sync_api import expect

        _seed(self.db_path, None)
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/ecoute')
        expect(page.locator('[data-ecoute="bouton"]')).to_contain_text(
            'Aucun bouton en base', timeout=10000
        )
        expect(page.locator('[data-ecoute-action="lancer"]')).to_be_disabled()
