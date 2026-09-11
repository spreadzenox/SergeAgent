#!/usr/bin/env python3
"""MC P1 Système : registre sections + page îlots (rendu, clic, fuite)."""

from __future__ import annotations

import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.mc.projectors import (  # noqa: E402
    PAGE_SECTIONS,
    PROJECTORS,
    SLOW_SECTIONS,
)
from tests.mc_server_case import McBrowserCase  # noqa: E402


class SystemRegistryTests(unittest.TestCase):
    def test_registre_p1(self) -> None:
        sections = PAGE_SECTIONS['p1']
        self.assertEqual(
            sections,
            ['meta', 'ilots', 'scheduler', 'campagnes', 'population', 'email'],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('population', SLOW_SECTIONS)


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
                'INSERT INTO contacts(id, venture_id, display, email,'
                ' regime, funnel_state, created_at, updated_at)'
                " VALUES('p1','v1','Ada','ada@x.io','OUTBOUND',"
                "'CONTACTING',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO contacts(id, venture_id, display, email,'
                ' regime, funnel_state, created_at, updated_at)'
                " VALUES('p2','v1','Bob','bob@x.io','OUTBOUND','NEW',?,?)",
                (iso, iso),
            )
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
                'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
                ' intent_id, status, created_at, updated_at)'
                " VALUES('x1','v1','invoice',50.0,'in-1','overdue',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO work_items(id, kind, venture_id, status,'
                ' priority, idempotency_key, created_at, updated_at)'
                " VALUES('w1','email.send','v1','READY',0,'k-w1',?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO accounts_standing(id, venue, handle,'
                ' cooldown_until, updated_at) VALUES'
                "('s1','gmail','a@x.io',?,?)",
                (
                    (now + timedelta(hours=3)).isoformat(),  # → 'dans 2 h'
                    iso,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def _page_systeme(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/system')
        page.locator('.ilot-btn').first.wait_for(timeout=10000)
        return page

    def test_page_systeme_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_systeme()
        expect(page.locator('.ilot-btn')).to_have_count(11)
        expect(page.locator('[data-ilot="label"]')).to_have_text(
            'Ordonnanceur'
        )
        expect(page.locator('[data-ilot="sante"]')).to_have_text('En forme')
        expect(page.locator('[data-ilot="resume"]')).to_have_text(
            '1 prêts, 0 en cours'
        )
        expect(
            page.get_by_role('button', name='Collecte — En erreur')
        ).to_be_visible()

    def test_clic_bouton_maj_panneau(self) -> None:
        from playwright.sync_api import expect

        page = self._page_systeme()
        page.get_by_role('button', name='Exécution — En forme').click()
        expect(page.locator('[data-ilot="label"]')).to_have_text('Exécution')
        expect(page.locator('[data-ilot="resume"]')).to_have_text(
            '0 en cours, 1 prêts'
        )
        actif = page.locator('.ilot-btn.actif')
        expect(actif).to_have_count(1)
        expect(actif).to_contain_text('Exécution')

    def test_pas_de_fuite_boucle_ilots(self) -> None:
        page = self._page_systeme()
        compte = (
            "(async () => (await import('/static/mc/hud.js')).hudActives())()"
        )
        self.assertEqual(page.evaluate(compte), 1)
        liens = page.locator('.barre-laterale nav a')
        liens.nth(6).click()  # Économie (page neutre, sans boucle)
        page.get_by_text('Cette page arrive dans un prochain lot.').wait_for(
            timeout=5000
        )
        self.assertEqual(page.evaluate(compte), 0)
        liens.nth(1).click()
        page.locator('.ilot-btn').first.wait_for(timeout=10000)
        self.assertEqual(page.evaluate(compte), 1)

    def test_clic_canvas_selectionne_ilot(self) -> None:
        from playwright.sync_api import expect

        page = self._page_systeme()
        cible = page.evaluate("""(async () => {
          const hud = await import('/static/mc/hud.js');
          const c = document.querySelector('[data-hud="ilots"]');
          const r = c.getBoundingClientRect();
          const pos = hud.dispositionIlots(11, c.width, c.height)[4];
          return {
            x: r.x + (pos.x / c.width) * r.width,
            y: r.y + (pos.y / c.height) * r.height,
          };
        })()""")
        page.mouse.click(cible['x'], cible['y'])
        expect(page.locator('[data-ilot="label"]')).to_have_text('Collecte')

    def test_sections_systeme_donnees(self) -> None:
        from playwright.sync_api import expect

        page = self._page_systeme()
        page.get_by_text('c1 — En cours').wait_for(timeout=10000)
        expect(page.locator('#sys-next')).to_have_text(
            'Prochain : email.send (v1).'
        )
        expect(page.locator('[data-section="scheduler"]')).to_contain_text(
            '1 prêts, 0 en cours, 0 bloqués.'
        )
        expect(page.locator('[data-section="campagnes"]')).to_contain_text(
            'c1 — En cours (email, 1/1 envoyés)'
        )
        expect(page.locator('[data-section="campagnes"]')).to_contain_text(
            'gmail a@x.io — dans 2 h.'
        )
        for text in (
            'CONTACTING : 1',
            'NEW : 1',
            'SMOKE_RUNNING : 1',
            'CANDIDATE : 1',
        ):
            expect(
                page.locator('[data-section="population"]')
            ).to_contain_text(text)
        expect(page.locator('[data-section="email"]')).to_contain_text(
            'sent : 1'
        )
        expect(page.locator('#sys-email-acti')).to_contain_text(
            'Dernière activité'
        )

    def test_sections_vides_gracieuses(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/system')
        page.locator('.ilot-btn').first.wait_for(timeout=10000)
        expect(page.locator('#sys-next')).to_have_text(
            'File vide, rien en attente.'
        )
        for section, text in (
            ('campagnes', 'Aucune campagne pour le moment.'),
            ('campagnes', 'Aucun compte en cooldown.'),
            ('population', 'Aucun contact.'),
            ('population', 'Aucune venture.'),
            ('email', 'Aucun volume.'),
        ):
            expect(
                page.locator(f'[data-section="{section}"]')
            ).to_contain_text(text)
        expect(page.locator('#sys-email-acti')).to_have_text(
            'Aucune activité.'
        )
