#!/usr/bin/env python3
"""MC Policy : les réglages des invocations et les quotas marqués « policy ».

Scénario : la page Policy montre « nombre d'idées » de « Formuler des
business A » et le quota des places de test ; Julien passe le nombre
d'idées à 2 et l'enregistre ; la base est à jour et le changement est au journal.
Une valeur hors bornes, un réglage inconnu ou un quota non entier sont
refusés.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McBrowserCase  # noqa: E402

REGLAGE = {
    'cible': 'invocation',
    'invocation_id': 'formuler_a',
    'name': 'nombre_idees',
}


class McReglagesTests(McBrowserCase):
    def _valeur(self) -> str:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT value FROM invocation_settings'
                " WHERE invocation_id='formuler_a' AND name='nombre_idees'"
            ).fetchone()[0]
        finally:
            conn.close()

    def test_changer_un_reglage_depuis_la_page(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/policy')
        section = page.locator('[data-section="reglages"]')
        expect(section).to_contain_text(
            'Formuler des business A', timeout=10000
        )
        expect(section).to_contain_text('Places de test occupées')
        ligne = section.locator('[data-reglage="formuler_a.nombre_idees"]')
        ligne.locator('input').fill('2')
        ligne.get_by_role('button', name='Enregistrer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Réglage enregistré'
        )
        self.assertEqual(self._valeur(), '2')
        conn = sqlite3.connect(self.db_path)
        acte = conn.execute(
            "SELECT payload_json FROM events WHERE type='mc_act'"
            ' ORDER BY id DESC LIMIT 1'
        ).fetchone()[0]
        conn.close()
        self.assertEqual(json.loads(acte)['apres'], '2')

    def test_valeurs_refusees(self) -> None:
        cookie = self._auth_cookie()
        for charge in (
            {**REGLAGE, 'value': '12'},
            {**REGLAGE, 'name': 'inconnu', 'value': '2'},
            {'cible': 'quota', 'id': 'places_de_test', 'value': 'trois'},
            {'cible': 'nuage', 'value': '1'},
        ):
            status, _, _ = self._api_post('/owner/api/reglage', charge, cookie)
            self.assertEqual(status, 400, charge)
        self.assertEqual(self._valeur(), '3')
        status, _, _ = self._api_post(
            '/owner/api/reglage',
            {'cible': 'quota', 'id': 'places_de_test', 'value': '5'},
            cookie,
        )
        self.assertEqual(status, 200)
