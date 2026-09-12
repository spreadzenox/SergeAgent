#!/usr/bin/env python3
"""MC API mutations politique (M4 édition, M5 rollback, M6 testing, M12 proposition) : tests."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.funnels.essai import ouvrir_essai  # noqa: E402
from serge.policy import load_policy  # noqa: E402
from serge.policy_snapshots import policy_en_vigueur  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402


class PolicyActesTests(McServerCase):
    def test_policy_edit_et_rollback(self) -> None:
        pol = load_policy()

        # Non auth -> 401
        status, _, _ = self._api_post(
            '/owner/api/policy/edit', {'policy': pol}
        )
        self.assertEqual(status, 401)

        cookie = self._auth_cookie()

        # Invalide -> 400
        status, _, _ = self._api_post(
            '/owner/api/policy/edit', {'policy': 'pas un dict'}, cookie
        )
        self.assertEqual(status, 400)

        # Valide -> 200 + snapshot
        pol_mod = dict(pol)
        pol_mod['budget'] = dict(pol['budget'])
        pol_mod['budget']['llm_daily_eur'] = 12.5
        status, _, corps = self._api_post(
            '/owner/api/policy/edit',
            {'policy': pol_mod, 'decision_id': 'dec_pol_1'},
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertTrue(data['ok'])
        snap_id = data['snapshot']['id']

        conn = open_db(self.db_path)
        try:
            ev = conn.execute(
                "SELECT payload_json FROM events WHERE type='mc_act' ORDER BY id DESC LIMIT 1"
            ).fetchone()
            ev_data = json.loads(ev[0])
            self.assertEqual(ev_data['acte'], 'policy_edit')
            self.assertEqual(ev_data['snapshot_id'], snap_id)
            self.assertEqual(
                policy_en_vigueur(conn)['budget']['llm_daily_eur'], 12.5
            )
            self.assertEqual(load_policy()['budget']['llm_daily_eur'], 5.0)
        finally:
            conn.close()

        # Rollback invalide -> 400 ou 404
        status, _, _ = self._api_post(
            '/owner/api/policy/rollback', {'snapshot_id': 0}, cookie
        )
        self.assertEqual(status, 400)
        status, _, _ = self._api_post(
            '/owner/api/policy/rollback', {'snapshot_id': 99999}, cookie
        )
        self.assertEqual(status, 404)

        # Rollback valide
        status, _, corps2 = self._api_post(
            '/owner/api/policy/rollback',
            {'snapshot_id': snap_id, 'decision_id': 'dec_roll_1'},
            cookie,
        )
        self.assertEqual(status, 200)
        data2 = json.loads(corps2.decode('utf-8'))
        self.assertTrue(data2['ok'])
        self.assertNotEqual(data2['snapshot']['id'], snap_id)

    def test_policy_testing_a_froid_et_lock(self) -> None:
        cookie = self._auth_cookie()

        # Test valide à froid (0 campagne)
        status, _, corps = self._api_post(
            '/owner/api/policy/testing',
            {'testing': {'n_smoke_min': 40}, 'decision_id': 'dec_test_1'},
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertEqual(data['testing']['n_smoke_min'], 40)
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
        finally:
            conn_live.close()

        # Activer une campagne -> verrouillage E3
        conn = open_db(self.db_path)
        try:
            conn.execute(
                'INSERT INTO campaigns(id, venture_id, family, channel, state, n_target, created_at, updated_at)'
                " VALUES('c1', 'v1', 'named', 'email', 'RUNNING', 10, 't', 't')"
            )
            conn.commit()
        finally:
            conn.close()

        status, _, corps_lock = self._api_post(
            '/owner/api/policy/testing',
            {'testing': {'n_smoke_min': 45}},
            cookie,
        )
        self.assertEqual(status, 409)

    def test_policy_propose_ticket(self) -> None:
        cookie = self._auth_cookie()

        status, _, _ = self._api_post(
            '/owner/api/policy/propose', {'titre': ''}, cookie
        )
        self.assertEqual(status, 400)

        status, _, corps = self._api_post(
            '/owner/api/policy/propose',
            {
                'titre': 'Ajuster seuil bandit',
                'diff': 'exploration: 0.1 -> 0.2',
                'justification': 'Plus de tests',
                'impact': 'faible',
                'decision_id': 'dec_prop_1',
            },
            cookie,
        )
        self.assertEqual(status, 200)
        data = json.loads(corps.decode('utf-8'))
        self.assertTrue(data['ok'])
        ticket_id = data['ticket_id']

        conn = open_db(self.db_path)
        try:
            t = conn.execute(
                'SELECT type, title, state FROM tickets WHERE id=?',
                (ticket_id,),
            ).fetchone()
            self.assertEqual(t[0], 'POLICY')
            self.assertEqual(t[1], 'Ajuster seuil bandit')
            self.assertEqual(t[2], 'DRAFT')
        finally:
            conn.close()


if __name__ == '__main__':
    unittest.main()
