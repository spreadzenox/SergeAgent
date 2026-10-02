#!/usr/bin/env python3
"""MC : changer un réglage de la page Policy, ou remettre sa valeur précédente."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.funnels.essai import ouvrir_essai  # noqa: E402
from serge.policy_store import policy_en_vigueur  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class PolicyActesTests(McServerCase):
    def _regler(self, cookie, charge):
        status, _, corps = self._api_post('/owner/api/reglage', charge, cookie)
        return status, json.loads(corps.decode('utf-8'))

    def test_un_reglage_general_puis_sa_valeur_precedente(self) -> None:
        charge = {'cible': 'policy', 'id': 'budget.llm_daily_eur'}
        status, _, _ = self._api_post(
            '/owner/api/reglage', {**charge, 'value': 12.5}
        )
        self.assertEqual(status, 401)
        cookie = self._auth_cookie()
        self.assertEqual(
            self._regler(cookie, {**charge, 'value': 'beaucoup'})[0], 400
        )
        self.assertEqual(
            self._regler(cookie, {**charge, 'value': 12.5})[0], 200
        )
        conn = open_db(self.db_path)
        try:
            self.assertEqual(
                policy_en_vigueur(conn)['budget']['llm_daily_eur'], 12.5
            )
            ev = conn.execute(
                'SELECT e.payload_json FROM events e JOIN event_rows r'
                " ON r.event_id=e.id WHERE r.table_name='policy_settings'"
                " AND r.row_id='budget.llm_daily_eur'"
            ).fetchone()
            self.assertEqual(json.loads(ev[0])['apres'], 12.5)
        finally:
            conn.close()
        status, _, _ = self._api_post(
            '/owner/api/reglage/precedent', charge, cookie
        )
        self.assertEqual(status, 200)
        conn = open_db(self.db_path)
        try:
            self.assertEqual(
                policy_en_vigueur(conn)['budget']['llm_daily_eur'], 5.0
            )
        finally:
            conn.close()

    def test_taille_des_essais_puis_verrou(self) -> None:
        cookie = self._auth_cookie()
        charge = {'cible': 'policy', 'id': 'testing.n_smoke_min'}
        self.assertEqual(self._regler(cookie, {**charge, 'value': 40})[0], 200)
        conn_live = open_db(self.db_path)
        try:
            conn_live.execute(
                'INSERT INTO ventures(id, lifecycle, schedulable,'
                " created_at, updated_at) VALUES('v-essai','SMOKE_RUNNING',"
                "1,'t','t')"
            )
            cid = ouvrir_essai(conn_live, 'v-essai', 'named', 'email', 'smoke')
            n = conn_live.execute(
                'SELECT n_target FROM campaigns WHERE id=?', (cid,)
            ).fetchone()[0]
            self.assertEqual(n, 40)
            # Activer une campagne verrouille la taille des essais.
            conn_live.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel, state,'
                ' n_target, created_at, updated_at)'
                " VALUES('c1', 'v1', 'named', 'email', 'RUNNING', 10, 't', 't')"
            )
            conn_live.commit()
        finally:
            conn_live.close()
        self.assertEqual(self._regler(cookie, {**charge, 'value': 45})[0], 409)

    def test_reglage_d_invocation_et_quota_remis(self) -> None:
        cookie = self._auth_cookie()
        reglage = {
            'cible': 'invocation',
            'invocation_id': 'formuler_a',
            'name': 'nombre_idees',
        }
        quota = {'cible': 'quota', 'id': 'places_de_test'}
        conn = open_db(self.db_path)
        try:
            avant = conn.execute(
                'SELECT value FROM invocation_settings'
                " WHERE invocation_id='formuler_a' AND name='nombre_idees'"
            ).fetchone()[0]
            avant_quota = conn.execute(
                "SELECT max_value FROM table_quotas WHERE id='places_de_test'"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(
            self._regler(cookie, {**reglage, 'value': '4'})[0], 200
        )
        self.assertEqual(self._regler(cookie, {**quota, 'value': '5'})[0], 200)
        for charge in (reglage, quota):
            status, _, _ = self._api_post(
                '/owner/api/reglage/precedent', charge, cookie
            )
            self.assertEqual(status, 200)
        conn = open_db(self.db_path)
        try:
            self.assertEqual(
                tuple(
                    conn.execute(
                        'SELECT value, previous_value FROM invocation_settings'
                        " WHERE invocation_id='formuler_a'"
                        " AND name='nombre_idees'"
                    ).fetchone()
                ),
                (avant, '4'),
            )
            self.assertEqual(
                tuple(
                    conn.execute(
                        'SELECT max_value, previous_value FROM table_quotas'
                        " WHERE id='places_de_test'"
                    ).fetchone()
                ),
                (avant_quota, 5),
            )
        finally:
            conn.close()

    def test_sans_valeur_precedente(self) -> None:
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/reglage/precedent',
            {'cible': 'policy', 'id': 'budget.monthly_eur'},
            cookie,
        )
        self.assertEqual(status, 409)

    def test_anciennes_routes_retirees(self) -> None:
        cookie = self._auth_cookie()
        for chemin in ('/owner/api/policy/edit', '/owner/api/policy/testing'):
            self.assertEqual(self._api_post(chemin, {}, cookie)[0], 404)

    def test_policy_propose_retire(self) -> None:
        """« Demander un changement » est retiré (Q68) : rien ne s'en servait."""
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/policy/propose', {'titre': 'x', 'diff': 'y'}, cookie
        )
        self.assertEqual(status, 404)


if __name__ == '__main__':
    unittest.main()
