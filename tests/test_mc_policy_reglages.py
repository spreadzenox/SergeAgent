#!/usr/bin/env python3
"""MC Policy : les réglages des invocations et les quotas marqués « policy ».

Scénario : la page Policy montre « nombre d'idées » de « Formuler des idées
(démo) » et le quota des business choisis ; Julien passe le nombre d'idées
à 3 et l'enregistre ; la base est à jour et le changement est au journal.
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
    'invocation_id': 'demo_formuler',
    'name': 'nombre_idees',
}


class McReglagesTests(McBrowserCase):
    def _valeur(self) -> str:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT value FROM invocation_settings'
                " WHERE invocation_id='demo_formuler' AND name='nombre_idees'"
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
            'Formuler des idées (démo)', timeout=10000
        )
        expect(section).to_contain_text('Au plus 3 business choisis')
        ligne = section.locator('.ligne-reglage').filter(
            has_text="Le nombre d'idées"
        )
        ligne.locator('input').fill('3')
        ligne.get_by_role('button', name='Enregistrer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Réglage enregistré'
        )
        self.assertEqual(self._valeur(), '3')
        conn = sqlite3.connect(self.db_path)
        acte = conn.execute(
            "SELECT payload_json FROM events WHERE type='mc_act'"
            ' ORDER BY id DESC LIMIT 1'
        ).fetchone()[0]
        conn.close()
        self.assertEqual(json.loads(acte)['apres'], '3')

    def test_valeurs_refusees(self) -> None:
        cookie = self._auth_cookie()
        for charge in (
            {**REGLAGE, 'value': '12'},
            {**REGLAGE, 'name': 'inconnu', 'value': '2'},
            {'cible': 'quota', 'id': 'business_choisis', 'value': 'trois'},
            {'cible': 'nuage', 'value': '1'},
        ):
            status, _, _ = self._api_post('/owner/api/reglage', charge, cookie)
            self.assertEqual(status, 400, charge)
        self.assertEqual(self._valeur(), '2')
        status, _, _ = self._api_post(
            '/owner/api/reglage',
            {'cible': 'quota', 'id': 'business_choisis', 'value': '5'},
            cookie,
        )
        self.assertEqual(status, 200)
