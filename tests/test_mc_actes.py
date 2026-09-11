#!/usr/bin/env python3
"""MC actes tickets M1 : endpoint (passant/refusé) + parité Discord (E1)."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.store import open_db  # noqa: E402
from serge.discord.interactions import route_interaction  # noqa: E402
from serge.registry import load_ticket_types  # noqa: E402
from serge.tickets import create_ticket, publish  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402
from tests.test_discord_interactions import OWNER  # noqa: E402


# Miroir tests/test_discord_interactions._interaction (découplé).
def _interaction_discord(custom_id, interaction_id='9001'):
    return {
        'id': interaction_id,
        'token': 'tok-mc-parite',
        'member': {'user': {'id': OWNER}},
        'data': {'custom_id': custom_id, 'component_type': 2},
    }


class TicketActeTests(McServerCase):
    def _ticket_ouvert(self, conn, titre='Prix'):
        types = load_ticket_types()
        iso = datetime.now(UTC).isoformat()
        ticket_id = create_ticket(
            conn, types, 'VETO_AMONT', titre, {'decision': 'x'}, now=iso
        )
        publish(conn, ticket_id)
        conn.commit()
        return ticket_id

    def _etat(self, ticket_id):
        conn = open_db(self.db_path)
        try:
            return conn.execute(
                'SELECT state FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        finally:
            conn.close()

    def test_acte_ok(self) -> None:
        conn = open_db(self.db_path)
        ticket_id = self._ticket_ouvert(conn)
        conn.close()
        cookie = self._auth_cookie()
        status, _, corps = self._api_post(
            '/owner/api/ticket/acte',
            {
                'ticket_id': ticket_id,
                'acte': 'approuver',
                'note': 'vu, ok',
                'decision_id': 'a1',
            },
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(corps.decode('utf-8'))['outcome'], 'APPROVED'
        )
        self.assertEqual(self._etat(ticket_id), 'APPROVED')
        conn = open_db(self.db_path)
        try:
            genres = {
                row[0]
                for row in conn.execute(
                    'SELECT kind FROM ticket_events WHERE ticket_id=?',
                    (ticket_id,),
                ).fetchall()
            }
            mc_act = conn.execute(
                "SELECT payload_json FROM events WHERE type='mc_act'"
                ' ORDER BY id DESC LIMIT 1'
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertIn('transition.approved', genres)
        self.assertIn('mc.approuver', genres)
        charge = json.loads(mc_act)
        self.assertEqual(
            (charge['acte'], charge['decision_id']), ('ticket', 'a1')
        )

    def test_acte_idempotent(self) -> None:
        conn = open_db(self.db_path)
        ticket_id = self._ticket_ouvert(conn)
        conn.close()
        cookie = self._auth_cookie()
        charge = {
            'ticket_id': ticket_id,
            'acte': 'rejeter',
            'decision_id': 'a2',
        }
        for _ in range(2):
            status, _, corps = self._api_post(
                '/owner/api/ticket/acte', charge, cookie
            )
            self.assertEqual(status, 200)
        self.assertEqual(
            json.loads(corps.decode('utf-8'))['duplicata'], 'true'
        )
        conn = open_db(self.db_path)
        try:
            total = conn.execute(
                'SELECT COUNT(*) FROM ticket_events WHERE ticket_id=?'
                " AND kind='transition.rejected'",
                (ticket_id,),
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(total, 1)

    def test_acte_refus(self) -> None:
        conn = open_db(self.db_path)
        ticket_id = self._ticket_ouvert(conn)
        conn.close()
        cookie = self._auth_cookie()
        cas = [
            ({'ticket_id': 't-zzz', 'acte': 'approuver'}, 404),
            ({'ticket_id': ticket_id, 'acte': 'bruler'}, 400),
            ({'ticket_id': ticket_id, 'acte': 'editer', 'note': ''}, 400),
            ({'acte': 'approuver'}, 400),
            ('{pas json', 400),
        ]
        for charge, code in cas:
            with self.subTest(charge=charge):
                status, _, _ = self._api_post(
                    '/owner/api/ticket/acte', charge, cookie
                )
                self.assertEqual(status, code)
        status, _, _ = self._api_post(
            '/owner/api/ticket/acte',
            {'ticket_id': ticket_id, 'acte': 'approuver'},
        )
        self.assertEqual(status, 401)
        status, _, _ = self._api_post(
            '/owner/api/ticket/acte',
            {'ticket_id': ticket_id, 'acte': 'approuver'},
            cookie,
        )
        self.assertEqual(status, 200)
        status, _, _ = self._api_post(
            '/owner/api/ticket/acte',
            {'ticket_id': ticket_id, 'acte': 'rejeter'},
            cookie,
        )
        self.assertEqual(status, 409)

    def test_parite_discord_mc(self) -> None:
        conn = open_db(self.db_path)
        t_discord = self._ticket_ouvert(conn, 'Prix D')
        t_mc = self._ticket_ouvert(conn, 'Prix M')
        t_cross = self._ticket_ouvert(conn, 'Prix X')
        conn.close()
        conn = open_db(self.db_path)
        try:
            resultat = route_interaction(
                conn,
                _interaction_discord(f't:{t_discord}:approuver'),
                OWNER,
            )
            conn.commit()
        finally:
            conn.close()
        self.assertEqual(resultat['status'], 'applied')
        cookie = self._auth_cookie()
        status, _, _ = self._api_post(
            '/owner/api/ticket/acte',
            {
                'ticket_id': t_mc,
                'acte': 'approuver',
                'decision_id': 'mc-parite-1',
            },
            cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(self._etat(t_discord), self._etat(t_mc))
        self.assertEqual(self._etat(t_mc), 'APPROVED')
        conn = open_db(self.db_path)
        try:
            genres_discord = {
                row[0]
                for row in conn.execute(
                    'SELECT kind FROM ticket_events WHERE ticket_id=?',
                    (t_discord,),
                ).fetchall()
            }
            genres_mc = {
                row[0]
                for row in conn.execute(
                    'SELECT kind FROM ticket_events WHERE ticket_id=?',
                    (t_mc,),
                ).fetchall()
            }
        finally:
            conn.close()
        self.assertIn('discord.approuver', genres_discord)
        self.assertIn('mc.approuver', genres_mc)
        conn = open_db(self.db_path)
        try:
            route_interaction(
                conn,
                _interaction_discord(
                    f't:{t_cross}:approuver', interaction_id='9002'
                ),
                OWNER,
            )
            conn.commit()
        finally:
            conn.close()
        status, _, _ = self._api_post(
            '/owner/api/ticket/acte',
            {'ticket_id': t_cross, 'acte': 'rejeter'},
            cookie,
        )
        self.assertEqual(status, 409)
