#!/usr/bin/env python3
"""MC P5 Politique : registre + rendu sections + testing froid + snapshots + trust."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class PolicyRegistryTests(unittest.TestCase):
    def test_registre_p5(self) -> None:
        sections = PAGE_SECTIONS['p5']
        self.assertEqual(sections, ['meta', 'politique_active', 'reglages'])
        for section in sections:
            self.assertIn(section, PROJECTORS)
        # Un réglage enregistré se voit tout de suite : pas de cache lent.
        self.assertNotIn('politique_active', SLOW_SECTIONS)


class McPolicyTests(McBrowserCase):
    def _page_policy(self):
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/policy')
        page.locator('[data-section="politique_active"]').wait_for(
            timeout=10000
        )
        return page

    def test_page_policy_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        regles = page.locator('[data-section="politique_active"]')
        expect(regles).to_contain_text('Argent')
        expect(regles).to_contain_text('Plafond du mois')
        # La taille des essais est une famille comme les autres.
        expect(regles).to_contain_text('Taille des essais')
        expect(regles).to_contain_text('Lecture du web')
        # Ce qui touche au modèle est sur la page Pipeline (Q68).
        expect(regles).not_to_contain_text('Appels au modèle')
        # Retirés (Q68) : rien ne s'en servait.
        expect(
            page.locator('[data-section="trust_candidates"]')
        ).to_have_count(0)
        expect(page.locator('[data-action="proposer-policy"]')).to_have_count(
            0
        )

    def test_enregistrer_puis_remettre_la_valeur_precedente(self) -> None:
        from playwright.sync_api import expect

        page = self._page_policy()
        page.locator(
            'button.onglet-policy', has_text='Taille des essais'
        ).click()
        champ = page.locator(
            '.champ-policy[data-chemin="testing.n_smoke_min"]'
        )
        nombre = champ.locator('input[type="number"]')
        nombre.fill('42')
        with page.expect_response('**/owner/api/reglage') as pending:
            champ.get_by_role('button', name='Enregistrer').click()
        self.assertEqual(pending.value.status, 200)
        remettre = champ.get_by_role('button', name='Remettre 30')
        expect(remettre).to_be_visible(timeout=10000)
        expect(nombre).to_have_value('42')
        with page.expect_response('**/owner/api/reglage/precedent') as pending:
            remettre.click()
        self.assertEqual(pending.value.status, 200)
        expect(champ.get_by_role('button', name='Remettre 42')).to_be_visible(
            timeout=10000
        )
        expect(nombre).to_have_value('30')

    def test_famille_verrouillee_pendant_un_essai(self) -> None:
        from playwright.sync_api import expect

        conn = open_db(self.db_path)
        try:
            conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel, state,'
                ' n_target, created_at, updated_at)'
                " VALUES('c1', 'v1', 'named', 'email', 'RUNNING', 10, 't', 't')"
            )
            conn.commit()
        finally:
            conn.close()
        page = self._page_policy()
        page.locator(
            'button.onglet-policy', has_text='Taille des essais'
        ).click()
        expect(page.locator('[data-verrou="testing"]')).to_contain_text(
            'Un essai tourne'
        )
        champ = page.locator(
            '.champ-policy[data-chemin="testing.n_smoke_min"]'
        )
        expect(
            champ.get_by_role('button', name='Enregistrer')
        ).to_be_disabled()


if __name__ == '__main__':
    unittest.main()
