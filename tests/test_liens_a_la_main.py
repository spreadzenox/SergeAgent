#!/usr/bin/env python3
"""Passer un lien à la main, depuis sa fiche dans Mission Control.

Scénario : le lien « Le cycle ouvert part en exploration » de l'étape 1
est réglé à la main. Le bouton ouvre un cycle ; « Explorer le web » n'est
pas lancée : le passage attend, avec son paramètre ``cycle_id``. Julien
clique sur « Passer à la suite » : la tâche est créée avec ce paramètre,
et le passage ne peut plus être relancé. Puis il remet le lien en
automatique.

Le passage qui attend ouvre aussi un ticket « Passage », envoyé à chaque
administrateur (Q62) : son feu vert fait passer ; un passage fait depuis
Mission Control annule le ticket.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.flow import (  # noqa: E402
    fire_button,
    pass_waiting,
    set_link_auto,
)
from serge.interpreter.queue import process_one  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from serge.tickets.admins import add_admin  # noqa: E402
from tests.mc_server_case import McBrowserCase  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'
LIEN = 'cycle_ouvert_vers_exploration'


def _ouvrir_un_cycle_a_la_main(conn: sqlite3.Connection) -> str:
    """Règle le lien à la main, ouvre un cycle ; rend la référence."""
    set_heartbeat(conn, True)
    set_link_auto(conn, LIEN, False)
    fire_button(conn, 'lancer_cycle', {'guide': 'artisans'})
    process_one(conn, 'works', now=NOW)
    conn.commit()
    cycle = conn.execute('SELECT id FROM listen_cycles').fetchone()[0]
    return f'listen_cycles:{cycle}'


def _taches(conn: sqlite3.Connection) -> list[tuple]:
    return conn.execute(
        'SELECT t.invocation_id, p.value FROM tasks t'
        " JOIN task_params p ON p.task_id=t.id AND p.name='cycle_id'"
        " WHERE t.invocation_id='explorer_web'"
    ).fetchall()


class PasserALaMainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.ref = _ouvrir_un_cycle_a_la_main(self.conn)
        self.cycle = self.ref.split(':')[1]

    def test_le_passage_attend_avec_ses_parametres(self) -> None:
        self.assertEqual(_taches(self.conn), [])
        fiche = project_objet(self.conn, 'lien', LIEN)
        assert fiche is not None
        attente = next(
            c for c in fiche['cadres'] if c['titre'] == 'Ce qui attend un clic'
        )
        self.assertEqual(attente['texte'], '1 passage(s) en attente.')
        self.assertIn(f'cycle_id = {self.cycle}', attente['champs'][0]['v'])
        self.assertEqual(
            attente['actions'][0]['charge'],
            {'link_id': LIEN, 'source_ref': self.ref},
        )
        inv = project_objet(self.conn, 'llm', 'ouvrir_cycle')
        assert inv is not None
        suite = next(
            c
            for c in inv['cadres']
            if c['titre'] == 'Ce qu’elle lance ensuite'
        )
        self.assertIn(
            '(passage à la main, 1 en attente)', suite['liens'][0]['titre']
        )

    def test_passer_a_la_suite(self) -> None:
        task_id = pass_waiting(self.conn, LIEN, self.ref)
        self.assertIsNotNone(task_id)
        self.assertEqual(_taches(self.conn), [('explorer_web', self.cycle)])
        self.assertIsNone(pass_waiting(self.conn, LIEN, self.ref))
        fiche = project_objet(self.conn, 'lien', LIEN)
        assert fiche is not None
        self.assertEqual(
            fiche['tableau']['lignes'][0]['cellules'][1:], [self.ref, task_id]
        )

    def test_rien_ne_passe_vers_une_invocation_eteinte(self) -> None:
        self.conn.execute(
            "UPDATE invocations SET enabled=0 WHERE id='explorer_web'"
        )
        self.assertIsNone(pass_waiting(self.conn, LIEN, self.ref))
        self.assertEqual(
            self.conn.execute(
                'SELECT passed_at FROM link_passages WHERE link_id=?', (LIEN,)
            ).fetchone(),
            ('',),
        )

    def test_l_interrupteur_ne_vaut_que_pour_la_suite(self) -> None:
        set_link_auto(self.conn, LIEN, True)
        fiche = project_objet(self.conn, 'lien', LIEN)
        assert fiche is not None
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(champs['Passage automatique'], 'oui')
        self.assertEqual(_taches(self.conn), [])


class TicketDePassageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.ref = _ouvrir_un_cycle_a_la_main(self.conn)

    def _ticket(self) -> tuple:
        return tuple(
            self.conn.execute(
                'SELECT id, state, ref_table, ref_id, payload_json FROM'
                " tickets WHERE type='PASSAGE'"
            ).fetchone()
        )

    def test_un_ticket_s_ouvre_et_son_feu_vert_fait_passer(self) -> None:
        from serge.discord.interactions import route_interaction

        ticket_id, state, table, ref, payload = self._ticket()
        self.assertEqual(
            (state, table, ref),
            ('OPEN', 'link_passages', f'{LIEN}:{self.ref}'),
        )
        self.assertIn('cycle_id = ', payload)
        add_admin(self.conn, '111122223333444455', 'Clem', 'test')
        resultat = route_interaction(
            self.conn,
            {
                'id': '8001',
                'type': 3,
                'user': {'id': '111122223333444455'},
                'data': {'custom_id': f't:{ticket_id}:passer'},
            },
        )
        self.assertEqual(resultat['status'], 'applied')
        self.conn.commit()
        process_one(self.conn, 'conversations', now=NOW)
        self.assertEqual([r[0] for r in _taches(self.conn)], ['explorer_web'])
        self.assertEqual(self._ticket()[1], 'APPROVED')

    def test_passer_dans_mission_control_annule_le_ticket(self) -> None:
        self.assertIsNotNone(pass_waiting(self.conn, LIEN, self.ref))
        self.assertEqual(self._ticket()[1], 'CANCELLED')


class PasserALaMainFrontTests(McBrowserCase):
    def _preparer(self) -> str:
        conn = sqlite3.connect(self.db_path)
        try:
            return _ouvrir_un_cycle_a_la_main(conn)
        finally:
            conn.close()

    def _base(self, sql: str) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(sql).fetchall()
        finally:
            conn.close()

    def test_passer_puis_remettre_en_automatique(self) -> None:
        from playwright.sync_api import expect

        ref = self._preparer()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/lien/{LIEN}')
        fiche = page.locator('#page')
        expect(fiche).to_contain_text(
            '1 passage(s) en attente.', timeout=10000
        )
        page.get_by_role('button', name=f'Passer à la suite : {ref}').click()
        expect(fiche).to_contain_text('Rien n’attend.')
        self.assertEqual(
            self._base(
                "SELECT COUNT(*) FROM tasks WHERE invocation_id='explorer_web'"
            ),
            [(1,)],
        )
        page.get_by_role('button', name='Passer en automatique').click()
        page.locator('.modale').get_by_role(
            'button', name='Passer en automatique'
        ).click()
        expect(fiche).to_contain_text('Passer à la main')
        self.assertEqual(
            self._base(f"SELECT auto FROM links WHERE id='{LIEN}'"), [(1,)]
        )

    def test_un_passage_ne_se_relance_pas(self) -> None:
        ref = self._preparer()
        cookie = self._auth_cookie()
        charge = {'link_id': LIEN, 'source_ref': ref}
        status, _, _ = self._api_post('/owner/api/lien/passer', charge, cookie)
        self.assertEqual(status, 200)
        status, _, _ = self._api_post('/owner/api/lien/passer', charge, cookie)
        self.assertEqual(status, 409)
        status, _, _ = self._api_post(
            '/owner/api/lien/auto', {'link_id': LIEN}, cookie
        )
        self.assertEqual(status, 400)


if __name__ == '__main__':
    unittest.main()
