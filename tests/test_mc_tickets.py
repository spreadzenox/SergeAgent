#!/usr/bin/env python3
"""MC P3 Décisions : registre + liste/filtres + carte interactive (M1/M2/M3)."""

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


class TicketsRegistryTests(unittest.TestCase):
    def test_registre_p3(self) -> None:
        sections = PAGE_SECTIONS['p3']
        self.assertEqual(
            sections,
            [
                'meta',
                'tickets',
                'diffs',
                'metriques',
                'admins_discord',
                'types_tickets',
            ],
        )
        for section in sections:
            self.assertIn(section, PROJECTORS)
        self.assertIn('diffs', SLOW_SECTIONS)
        self.assertIn('metriques', SLOW_SECTIONS)


class McTicketsTests(McBrowserCase):
    def _fixtures(self) -> None:
        import sqlite3

        now = datetime.now(UTC)
        iso = now.isoformat()
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' expiry_at, created_at, updated_at) VALUES'
                "('t1','VETO_AMONT','Prix du lot','OPEN',"
                '\'{"decision": "augmenter"}\',?, ?,?)',
                (
                    (now + timedelta(minutes=30)).isoformat(),
                    iso,
                    iso,
                ),
            )
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' expiry_at, created_at, updated_at) VALUES'
                "('t2','MEMORY','Leçons','OPEN','{}',?, ?,?)",
                (
                    (now + timedelta(hours=20)).isoformat(),
                    iso,
                    iso,
                ),
            )
            conn.execute(
                'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
                " VALUES('i1','t2','MEMORY','Leçon A','open'),"
                "('i2','t2','MEMORY','Leçon B','open')"
            )
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' expiry_at, created_at, updated_at) VALUES'
                "('t3','GUICHET','Captcha','APPROVED','{}','', ?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO tickets(id, type, title, state, payload_json,'
                ' expiry_at, created_at, updated_at) VALUES'
                "('t4','POLICY','Plafond','OPEN',"
                '\'{"diff_avant_apres": "diff-5-7", "justification": "pic-conso"}\','
                "'', ?,?)",
                (iso, iso),
            )
            conn.execute(
                'INSERT INTO ticket_items(id, ticket_id, kind, label, state, payload_json)'
                " VALUES('i-edit','t2','MEMORY','avant-vieux','edit','{\"label\": \"apres-neuf\"}')"
            )
            for n in range(1, 12):
                conn.execute(
                    'INSERT INTO ticket_items(id, ticket_id, kind, label, state)'
                    " VALUES(?,'t2','MEMORY',?,'open')",
                    (f'm{n}', f'Leçon extra {n}'),
                )
            conn.commit()
        finally:
            conn.close()

    def _page_tickets(self):
        self._fixtures()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/tickets')
        page.locator('.lien-ticket').first.wait_for(timeout=10000)
        return page

    def test_page_tickets_rendu(self) -> None:
        from playwright.sync_api import expect

        page = self._page_tickets()
        expect(page.locator('.lien-ticket')).to_have_count(4)
        expect(page.locator('[data-section="tickets"]')).to_contain_text(
            'VETO_AMONT — Prix du lot [OPEN]'
        )
        expect(page.locator('[data-section="tickets"]')).to_contain_text(
            'URGENT'
        )

    def test_filtres(self) -> None:
        from playwright.sync_api import expect

        page = self._page_tickets()
        page.select_option('[data-filtre="type"]', 'MEMORY')
        expect(page.locator('.lien-ticket')).to_have_count(1)
        page.select_option('[data-filtre="type"]', '')
        page.select_option('[data-filtre="etat"]', 'termines')
        expect(page.locator('.lien-ticket')).to_have_count(1)
        expect(page.locator('[data-section="tickets"]')).to_contain_text(
            'Captcha'
        )
        page.select_option('[data-filtre="etat"]', '')
        page.fill('[data-filtre="recherche"]', 'prix')
        expect(page.locator('.lien-ticket')).to_have_count(1)
        page.fill('[data-filtre="recherche"]', '')
        page.check('[data-filtre="urgents"]')
        expect(page.locator('.lien-ticket')).to_have_count(1)
        expect(page.locator('[data-section="tickets"]')).to_contain_text(
            'Prix du lot'
        )

    def test_carte_et_acte(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_tickets()
        page.locator('.lien-ticket[data-ticket="t1"]').click()
        carte = page.locator('[data-carte="panneau"]')
        expect(carte).to_contain_text('VETO_AMONT — Prix du lot')
        expect(carte).to_contain_text('decision : augmenter')
        carte.get_by_role('button', name='Approuver').click()
        modale = page.locator('.modale')
        modale.get_by_role('button', name='Approuver').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Ticket approuvé.'
        )
        expect(carte).to_contain_text('État : APPROVED')
        conn = sqlite3.connect(self.db_path)
        try:
            etat = conn.execute(
                'SELECT state FROM tickets WHERE id=?', ('t1',)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(etat, 'APPROVED')

    def test_discuter(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_tickets()
        page.locator('.lien-ticket[data-ticket="t1"]').click()
        carte = page.locator('[data-carte="panneau"]')
        carte.get_by_role('button', name='Discuter').click()
        modale = page.locator('.modale')
        modale.locator('input').fill('On en parle ?')
        modale.get_by_role('button', name='Envoyer').click()
        expect(page.locator('.toast-succes')).to_contain_text(
            'Message envoyé.'
        )
        expect(carte).to_contain_text('État : DISCUSSING')
        conn = sqlite3.connect(self.db_path)
        try:
            etat = conn.execute(
                'SELECT state FROM tickets WHERE id=?', ('t1',)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(etat, 'DISCUSSING')

    def test_item_garder(self) -> None:
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_tickets()
        page.locator('.lien-ticket[data-ticket="t2"]').click()
        carte = page.locator('[data-carte="panneau"]')
        carte.locator('button[data-item="i1"]').first.click()
        expect(page.locator('.toast-succes')).to_contain_text('Item gardé.')
        conn = sqlite3.connect(self.db_path)
        try:
            etat = conn.execute(
                'SELECT state FROM ticket_items WHERE id=?', ('i1',)
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(etat, 'keep')

    def test_diffs_et_metriques(self) -> None:
        from playwright.sync_api import expect

        page = self._page_tickets()
        diffs = page.locator('[data-section="diffs"]')
        expect(diffs).to_contain_text('Plafond — diff-5-7')
        expect(diffs).to_contain_text('avant-vieux → apres-neuf')
        metriques = page.locator('[data-section="metriques"]')
        expect(metriques).to_contain_text('Backlog en cours : 3 ouverts')
        expect(metriques).to_contain_text('Taux d’approbation :')

    def test_administrateurs_et_types_de_tickets(self) -> None:
        """Ajouter puis retirer un administrateur Discord ; changer le délai
        d'un type de ticket (décisions Q85 et Q86)."""
        import sqlite3

        from playwright.sync_api import expect

        page = self._page_tickets()
        admins = page.locator('[data-section="admins_discord"]')
        expect(admins).to_contain_text('Aucun administrateur')
        form = admins.locator('[data-admins="ajout"]')
        form.locator('input[name="user_id"]').fill('123')
        form.locator('button[type="submit"]').click()
        expect(page.locator('.toast').last).to_contain_text('17 à 20 chiffres')
        form.locator('input[name="user_id"]').fill('111122223333444455')
        form.locator('input[name="name"]').fill('Clem')
        form.locator('button[type="submit"]').click()
        expect(admins).to_contain_text('Clem — 111122223333444455')
        admins.get_by_role('button', name='Retirer').click()
        page.locator('.modale').get_by_role('button', name='Retirer').click()
        expect(admins).to_contain_text('Aucun administrateur')
        types = page.locator('[data-section="types_tickets"]')
        bloc = types.locator('[data-type-ticket="QNA"]')
        expect(bloc).to_contain_text('aujourd’hui 3 j')
        bloc.locator('input[name="expiry_minutes"]').fill('120')
        bloc.get_by_role('button', name='Enregistrer').click()
        expect(types.locator('[data-type-ticket="QNA"]')).to_contain_text(
            'aujourd’hui 2 h'
        )
        conn = sqlite3.connect(self.db_path)
        try:
            delai = conn.execute(
                "SELECT expiry_minutes FROM ticket_types WHERE id='QNA'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(delai, 120)

    def test_memory_pagination_front(self) -> None:
        from playwright.sync_api import expect

        page = self._page_tickets()
        info = page.locator('[data-memory="info"]')
        expect(info).to_contain_text('Page 1 / 2 (14 propositions)')
        btn_next = page.locator('[data-memory="next"]')
        btn_prev = page.locator('[data-memory="prev"]')
        expect(btn_prev).to_be_disabled()
        expect(btn_next).to_be_enabled()
        btn_next.click()
        expect(info).to_contain_text('Page 2 / 2 (14 propositions)')
        expect(btn_prev).to_be_enabled()
        expect(btn_next).to_be_disabled()
