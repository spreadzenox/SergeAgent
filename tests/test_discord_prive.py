#!/usr/bin/env python3
"""Les tickets en message privé, chez chaque administrateur (Q85, Q86).

Scénarios :
- un ticket ouvert part en message privé à chaque administrateur ajouté
  avant lui, une seule fois ; un ticket plus ancien que l'administrateur
  reste dans Mission Control ;
- tranché par l'un (sur Discord) ou dans Mission Control, sa carte est
  mise à jour chez tous : boutons morts, et qui l'a tranché ;
- un message qui ne part pas est réessayé après 10 minutes, pas avant.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.discord.prive import deliver  # noqa: E402
from serge.discord.rest import DiscordError  # noqa: E402
from serge.tickets import create_ticket, decide, publish  # noqa: E402
from serge.tickets.admins import add_admin  # noqa: E402
from serge.tickets.types import ticket_types  # noqa: E402

JULIEN = '999988887777666555'
CLEM = '111122223333444455'
T0 = '2026-10-09T10:00:00+00:00'


class Discord:
    """Un faux Discord : un canal privé par personne, des messages."""

    def __init__(self) -> None:
        self.envoyes: list[tuple[str, dict]] = []
        self.edites: list[tuple[str, str, dict]] = []
        self.refuse: set[str] = set()

    def create_dm(self, _token: str, user_id: str) -> str:
        if user_id in self.refuse:
            raise DiscordError('API: 50007 Cannot send messages to this user')
        return f'dm-{user_id}'

    def send_message(self, _token: str, channel: str, carte: dict) -> dict:
        self.envoyes.append((channel, carte))
        return {'id': f'msg-{len(self.envoyes)}'}

    def edit_message(
        self, _token: str, channel: str, message: str, carte: dict
    ) -> dict:
        self.edites.append((channel, message, carte))
        return {'id': message}


class PriveTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.discord = Discord()
        patches = [
            mock.patch(
                f'serge.discord.prive.{nom}', getattr(self.discord, nom)
            )
            for nom in ('create_dm', 'send_message', 'edit_message')
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def tearDown(self) -> None:
        self.conn.close()

    def _admin(self, user_id: str, nom: str, quand: str) -> None:
        add_admin(self.conn, user_id, nom, 'test')
        self.conn.execute(
            'UPDATE discord_admins SET added_at=? WHERE user_id=?',
            (quand, user_id),
        )

    def _ticket(self, quand: str) -> str:
        ticket_id = create_ticket(
            self.conn,
            ticket_types(self.conn),
            'VETO_AMONT',
            'Créer le business',
            {'decision': 'x'},
            now=quand,
        )
        publish(self.conn, ticket_id)
        return ticket_id

    def _tranche(self, carte: dict) -> str:
        champs = carte['embeds'][0]['fields']
        return next((f['value'] for f in champs if f['name'] == 'Tranché'), '')

    def test_un_ticket_part_a_chaque_administrateur_une_fois(self) -> None:
        self._admin(JULIEN, 'Julien', T0)
        ancien = self._ticket('2026-10-09T09:00:00+00:00')
        self._admin(CLEM, 'Clem', '2026-10-09T10:30:00+00:00')
        nouveau = self._ticket('2026-10-09T11:00:00+00:00')
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00'), 2
        )
        self.assertEqual(
            sorted(c for c, _ in self.discord.envoyes),
            [f'dm-{CLEM}', f'dm-{JULIEN}'],
        )
        # Un ticket plus ancien que les administrateurs reste dans Mission
        # Control ; au tour suivant, rien ne repart.
        self.assertIsNone(
            self.conn.execute(
                'SELECT 1 FROM ticket_messages WHERE ticket_id=?', (ancien,)
            ).fetchone()
        )
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:02+00:00'), 0
        )
        boutons = self.discord.envoyes[0][1]['components'][0]['components']
        self.assertFalse(any(b['disabled'] for b in boutons))
        self.assertTrue(nouveau)

    def test_tranche_par_l_un_il_est_mis_a_jour_chez_tous(self) -> None:
        self._admin(JULIEN, 'Julien', T0)
        self._admin(CLEM, 'Clem', T0)
        ticket_id = self._ticket('2026-10-09T11:00:00+00:00')
        deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00')
        decide(
            self.conn,
            ticket_id,
            'APPROVED',
            actor=f'discord:{CLEM}',
            note='Vas-y',
        )
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:03+00:00'), 2
        )
        self.assertEqual(len(self.discord.edites), 2)
        for _canal, _message, carte in self.discord.edites:
            self.assertEqual(self._tranche(carte), 'Approuvé par Clem : Vas-y')
            boutons = carte['components'][0]['components']
            self.assertTrue(all(b['disabled'] for b in boutons))
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:04+00:00'), 0
        )

    def test_tranche_dans_mission_control(self) -> None:
        self._admin(JULIEN, 'Julien', T0)
        ticket_id = self._ticket('2026-10-09T11:00:00+00:00')
        deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00')
        decide(self.conn, ticket_id, 'REJECTED', actor='owner')
        deliver(self.conn, 'tok', '2026-10-09T11:00:02+00:00')
        self.assertEqual(
            self._tranche(self.discord.edites[0][2]),
            'Rejeté dans Mission Control',
        )

    def test_un_message_refuse_est_reessaye_plus_tard(self) -> None:
        self._admin(JULIEN, 'Julien', T0)
        self.discord.refuse.add(JULIEN)
        self._ticket('2026-10-09T11:00:00+00:00')
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00'), 0
        )
        self.discord.refuse.clear()
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:05:00+00:00'), 0
        )
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:11:00+00:00'), 1
        )


if __name__ == '__main__':
    unittest.main()
