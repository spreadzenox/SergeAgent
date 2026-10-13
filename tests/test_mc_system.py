#!/usr/bin/env python3
"""MC P1 Système : registre sections + page îlots (rendu, clic, fuite)."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402
from tests.taches_fixtures import invocations, tache  # noqa: E402


class SystemRegistryTests(unittest.TestCase):
    def test_registre_p1(self) -> None:
        sections = PAGE_SECTIONS['p1']
        self.assertEqual(
            sections,
            ['meta', 'ilots', 'essais', 'population', 'non_rattaches'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('population', SLOW_SECTIONS)
        # Les îlots lisent l'état des services : lents à sonder.
        self.assertIn('ilots', SLOW_SECTIONS)


class McSystemTests(McBrowserCase):
    def _fixtures(self) -> None:
        import sqlite3

        now = datetime.now(UTC)
        iso = now.isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO ventures(id, lifecycle, schedulable,'
                " created_at, updated_at) VALUES('v1','SMOKE_RUNNING',"
                '1,?,?)',
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO ventures(id, lifecycle, schedulable,'
                " created_at, updated_at) VALUES('v2','CANDIDATE',0,?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
                (
                    'p1',
                    'v1',
                    'Ada',
                    'OUTBOUND',
                    'CONTACTING',
                    iso,
                    iso,
                ),
            )
            add_address(conn, 'p1', 'email', 'ada@x.io')
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
                (
                    'p2',
                    'v1',
                    'Bob',
                    'OUTBOUND',
                    'NEW',
                    iso,
                    iso,
                ),
            )
            add_address(conn, 'p2', 'email', 'bob@x.io')
            conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel,'
                ' state, n_target, created_at, updated_at)'
                " VALUES('c1','v1','named','email','RUNNING',10,?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO touches(id, campaign_id, contact_id, channel,'
                ' status, idempotency_key, created_at, updated_at)'
                " VALUES('t1','c1','','email','sent','k-t1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO inbound_events(id, channel, address, subject,'
                " body, status, received_at) VALUES('i1', 'email',"
                " 'inconnu@ailleurs.fr', 'Une question', 'Bonjour',"
                " 'unattached', ?)",
                (iso,),
            )
            invocations(
                conn, ('envoyer', 'Envoyer un e-mail', 'prospection_light')
            )
            tache(conn, 'envoyer', {'venture_id': 'v1'}, key='k-w1')
            conn.commit()
        finally:
            conn.close()

    def _page_home(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/live')
        page.locator('.noeud').first.wait_for(timeout=10000)
        return page

    def test_system_accessible(self) -> None:
        from playwright.sync_api import expect

        page = self._page_home()
        page.goto(f'{self.base}/owner#/system')
        # Un îlot par morceau qui tourne ; un clic montre ses détails.
        ilots = page.locator('[data-ilots="liste"]')
        for label in ('Files de tâches', 'E-mail', 'Voix', 'Discord'):
            expect(ilots).to_contain_text(label)
        ilots.locator('[data-ilot="discord"]').click()
        expect(page.locator('[data-ilot="label"]')).to_have_text('Discord')
        page.locator('[data-ilot="email"]').click()
        expect(page.locator('[data-ilot="resume"]')).to_have_text(
            'Pas branché sur ce serveur.'
        )
        # Les boutons d'essai, déclarés en base, par l'identifiant de leur
        # déclencheur : le bout en bout, le chantier et l'interface web
        # (lot 10), puis les canaux.
        essais = page.locator('[data-section="essais"]')
        expect(essais.locator('[data-bouton-base]')).to_have_text(
            [
                "Bout en bout : le POC d'une calculatrice",
                "Bout en bout : le produit fini d'une calculatrice",
                'Essayer le chantier',
                "Essayer l'étape 2",
                "Essayer l'interface web",
                'Lancer un essai',
                "Publier le chantier d'essai",
            ]
        )
        # Le message d'un inconnu : pas traité, mais visible.
        expect(page.locator('[data-section="non_rattaches"]')).to_contain_text(
            'inconnu@ailleurs.fr · Une question'
        )
        self.assertTrue(page.url.endswith('#/system'))

    def test_pas_de_fuite_boucle_ilots(self) -> None:
        page = self._page_home()
        compte = (
            "(async () => (await import('/static/mc/hud.js')).hudActives())()"
        )
        self.assertEqual(page.evaluate(compte), 1)
        liens = page.locator('.barre-laterale nav a')
        liens.nth(7).click()
        page.locator('[data-section="charte_metriques"]').wait_for(
            timeout=10000
        )
        self.assertEqual(page.evaluate(compte), 0)
        liens.nth(0).click()
        page.locator('.noeud').first.wait_for(timeout=10000)
        self.assertEqual(page.evaluate(compte), 1)

    def test_sections_systeme_donnees(self) -> None:
        from playwright.sync_api import expect

        page = self._page_home()
        expect(page.locator('[data-section="business"]')).to_contain_text(
            'Smoke en cours'
        )
        expect(page.locator('[data-section="business"]')).not_to_contain_text(
            'SMOKE_RUNNING'
        )
        expect(page.locator('#voix-noyau')).not_to_have_text('…')

    def test_sections_vides_gracieuses(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/live')
        page.locator('#live-headline').wait_for(timeout=10000)
        expect(page.locator('#page')).to_contain_text('Serge est arrêté')
        expect(page.locator('#page')).to_contain_text('File vide')
