#!/usr/bin/env python3
"""MC : les actions sur le pipeline, depuis la fiche d'un objet.

Scénario 1 : une tâche a échoué ; sa fiche montre « Relancer la tâche » ;
un clic la remet dans sa file, prête, sans son erreur. Une tâche qui n'a
pas échoué ne peut pas être relancée.

Scénario 2 : sur la fiche de « Formuler des business A », Julien retire
les business des tables qu'elle voit pour comparer, puis les remet (les
pages gardées lui sont retirées dès le départ). Une
table qui n'est pas décrite en base ne peut pas être ajoutée.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.mc_server_case import McBrowserCase  # noqa: E402
from tests.taches_fixtures import invocations, tache  # noqa: E402


class RelancerTacheTests(McBrowserCase):
    def _taches(self) -> tuple[str, str]:
        conn = sqlite3.connect(self.db_path)
        invocations(
            conn, ('envoyer', 'Envoyer un e-mail', 'prospection_light')
        )
        echec = tache(
            conn,
            'envoyer',
            {'n': '1'},
            key='k1',
            status='failed',
            error='boum',
        )
        faite = tache(conn, 'envoyer', {'n': '2'}, key='k2', status='done')
        conn.commit()
        conn.close()
        return echec, faite

    def _etat(self, task_id: str) -> tuple:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT status, last_error FROM tasks WHERE id=?', (task_id,)
            ).fetchone()
        finally:
            conn.close()

    def test_relancer_depuis_la_fiche(self) -> None:
        from playwright.sync_api import expect

        echec, _ = self._taches()
        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/task/{echec}')
        bouton = page.get_by_role('button', name='Relancer la tâche')
        bouton.click(timeout=10000)
        page.locator('.modale').get_by_role(
            'button', name='Relancer la tâche'
        ).click()
        expect(page.locator('.toast-succes')).to_contain_text('fait')
        expect(page.locator('#page')).to_contain_text('Prête')
        self.assertEqual(self._etat(echec), ('ready', ''))

    def test_annuler_une_tache_en_attente(self) -> None:
        conn = sqlite3.connect(self.db_path)
        invocations(
            conn, ('envoyer', 'Envoyer un e-mail', 'prospection_light')
        )
        attente = tache(conn, 'envoyer', {'n': '3'}, key='k3')
        faite = tache(conn, 'envoyer', {'n': '4'}, key='k4', status='done')
        conn.commit()
        conn.close()
        from serge.mc.proj_taches import fiche_tache

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        fiche = fiche_tache(conn, attente)
        conn.close()
        assert fiche is not None
        self.assertEqual(
            [a['libelle'] for a in fiche['actions']], ['Annuler la tâche']
        )
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/tache/annuler', {'task_id': attente}, cookie
        )
        self.assertEqual(status, 200)
        self.assertEqual(self._etat(attente)[0], 'cancelled')
        status, _, _ = self._api_post(
            '/owner/api/tache/annuler', {'task_id': faite}, cookie
        )
        self.assertEqual(status, 409)
        self.assertEqual(self._etat(faite)[0], 'done')

    def test_une_tache_finie_ne_se_relance_pas(self) -> None:
        _, faite = self._taches()
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/tache/relancer', {'task_id': faite}, cookie
        )
        self.assertEqual(status, 409)
        self.assertEqual(self._etat(faite)[0], 'done')


class ComparerTests(McBrowserCase):
    def _ajustements(self) -> list[tuple]:
        conn = sqlite3.connect(self.db_path)
        try:
            return conn.execute(
                'SELECT table_name, included FROM invocation_compare_tables'
                " WHERE invocation_id='formuler_a' ORDER BY table_name"
            ).fetchall()
        finally:
            conn.close()

    def test_retirer_puis_remettre_une_table(self) -> None:
        from playwright.sync_api import expect

        page = self._auth_context().new_page()
        self._watch_errors(page)
        page.goto(f'{self.base}/owner#/objet/llm/formuler_a')
        page.get_by_role('button', name='Retirer « Les business »').click(
            timeout=10000
        )
        expect(page.locator('#page')).to_contain_text(
            'id, name — retirée à la main'
        )
        self.assertEqual(
            self._ajustements(), [('listen_docs', 0), ('ventures', 0)]
        )
        page.get_by_role('button', name='Remettre « Les business »').click(
            timeout=10000
        )
        expect(page.locator('#page')).to_contain_text(
            'id, name — elle y écrit'
        )
        self.assertEqual(self._ajustements(), [('listen_docs', 0)])

    def test_une_table_non_decrite_est_refusee(self) -> None:
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/invocation/comparer',
            {
                'invocation_id': 'formuler_a',
                'table': 'transactions',
                'voir': True,
            },
            cookie,
        )
        self.assertEqual(status, 409)
        status, _, _ = self._api_post(
            '/owner/api/invocation/comparer',
            {'invocation_id': 'formuler_a', 'table': 'ventures'},
            cookie,
        )
        self.assertEqual(status, 400)
        self.assertEqual(self._ajustements(), [('listen_docs', 0)])
