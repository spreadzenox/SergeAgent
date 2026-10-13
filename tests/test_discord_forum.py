#!/usr/bin/env python3
"""Les tickets dans le forum « tickets » du serveur de Serge (Q88).

Scénarios :
- sans forum réglé, rien ne part : les tickets restent dans Mission
  Control ;
- un ticket ouvert après le réglage du forum y ouvre un fil, une seule
  fois, et mentionne les administrateurs ; un ticket plus ancien reste
  dans Mission Control ;
- tranché sur Discord ou dans Mission Control, sa carte est mise à jour
  (boutons morts, qui l'a tranché) et son fil archivé ; un fil archivé se
  rouvre le temps d'une nouvelle mise à jour ;
- un fil qui ne s'ouvre pas est réessayé après 10 minutes, pas avant ;
- un identifiant de forum mal écrit est refusé.
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
from serge.discord.forum import deliver, regler_forum  # noqa: E402
from serge.discord.rest import DiscordError  # noqa: E402
from serge.tickets import create_ticket, decide, publish  # noqa: E402
from serge.tickets.admins import add_admin  # noqa: E402
from serge.tickets.lifecycle import execute  # noqa: E402
from serge.tickets.types import ticket_types  # noqa: E402

JULIEN = '999988887777666555'
CLEM = '111122223333444455'
FORUM = '222233334444555566'
T0 = '2026-10-09T10:00:00+00:00'


class Discord:
    """Un faux Discord : un forum, ses fils, leurs cartes."""

    def __init__(self) -> None:
        self.fils: list[tuple[str, str, dict]] = []
        self.edites: list[tuple[str, dict]] = []
        self.archives: list[tuple[str, bool]] = []
        self.panne = False

    def create_forum_post(
        self, _token: str, forum: str, nom: str, message: dict
    ) -> str:
        if self.panne:
            raise DiscordError('API: Discord HTTP 403')
        self.fils.append((forum, nom, message))
        return f'fil-{len(self.fils)}'

    def edit_message(
        self, _token: str, fil: str, message: str, carte: dict
    ) -> dict:
        assert fil == message  # la carte est le premier message du fil
        self.edites.append((fil, carte))
        return {'id': message}

    def archive_thread(self, _token: str, fil: str, archived: bool) -> None:
        self.archives.append((fil, archived))


class ForumTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.discord = Discord()
        for nom in ('create_forum_post', 'edit_message', 'archive_thread'):
            patch = mock.patch(
                f'serge.discord.forum.{nom}', getattr(self.discord, nom)
            )
            patch.start()
            self.addCleanup(patch.stop)
        add_admin(self.conn, JULIEN, 'Julien', 'test')
        add_admin(self.conn, CLEM, 'Clem', 'test')

    def _forum(self, quand: str = T0) -> None:
        self.assertEqual(regler_forum(self.conn, FORUM, 'owner'), '')
        self.conn.execute(
            "UPDATE runtime_flags SET set_at=? WHERE name='discord.forum_tickets'",
            (quand,),
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

    def test_sans_forum_rien_ne_part(self) -> None:
        self._ticket('2026-10-09T11:00:00+00:00')
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00'), 0
        )
        self.assertEqual(self.discord.fils, [])

    def test_un_ticket_ouvre_un_fil_et_mentionne_les_admins(self) -> None:
        ancien = self._ticket('2026-10-09T09:00:00+00:00')
        self._forum()
        self._ticket('2026-10-09T11:00:00+00:00')
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00'), 1
        )
        forum, nom, message = self.discord.fils[0]
        self.assertEqual(forum, FORUM)
        self.assertIn('Créer le business', nom)
        self.assertEqual(message['content'], f'<@{JULIEN}> <@{CLEM}>')
        self.assertEqual(
            message['allowed_mentions'], {'parse': [], 'users': [JULIEN, CLEM]}
        )
        boutons = message['components'][0]['components']
        self.assertFalse(any(b['disabled'] for b in boutons))
        # Un ticket plus ancien que le forum reste dans Mission Control ;
        # au tour suivant, rien ne repart.
        self.assertIsNone(
            self.conn.execute(
                'SELECT 1 FROM ticket_posts WHERE ticket_id=?', (ancien,)
            ).fetchone()
        )
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:02+00:00'), 0
        )
        self.assertEqual(len(self.discord.fils), 1)

    def test_tranche_la_carte_suit_et_le_fil_est_archive(self) -> None:
        self._forum()
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
            deliver(self.conn, 'tok', '2026-10-09T11:00:03+00:00'), 1
        )
        fil, carte = self.discord.edites[0]
        self.assertEqual(fil, 'fil-1')
        self.assertEqual(self._tranche(carte), 'Approuvé par Clem : Vas-y')
        boutons = carte['components'][0]['components']
        self.assertTrue(all(b['disabled'] for b in boutons))
        self.assertEqual(self.discord.archives, [('fil-1', True)])
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:00:04+00:00'), 0
        )
        # Exécuté ensuite : le fil archivé se rouvre le temps de la mise à
        # jour, puis se referme.
        execute(self.conn, ticket_id)
        deliver(self.conn, 'tok', '2026-10-09T11:00:06+00:00')
        self.assertEqual(
            self.discord.archives,
            [('fil-1', True), ('fil-1', False), ('fil-1', True)],
        )

    def test_tranche_dans_mission_control(self) -> None:
        self._forum()
        ticket_id = self._ticket('2026-10-09T11:00:00+00:00')
        deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00')
        decide(self.conn, ticket_id, 'REJECTED', actor='owner')
        deliver(self.conn, 'tok', '2026-10-09T11:00:02+00:00')
        self.assertEqual(
            self._tranche(self.discord.edites[0][1]),
            'Rejeté dans Mission Control',
        )

    def test_un_fil_refuse_est_reessaye_plus_tard(self) -> None:
        self._forum()
        self.discord.panne = True
        ticket_id = self._ticket('2026-10-09T11:00:00+00:00')
        with mock.patch('serge.discord.forum.journal') as journal:
            self.assertEqual(
                deliver(self.conn, 'tok', '2026-10-09T11:00:01+00:00'), 0
            )
        # La raison donnée par Discord part au journal du bot.
        journal.assert_called_once_with(
            f'fil du ticket {ticket_id} pas ouvert : API: Discord HTTP 403'
        )
        self.discord.panne = False
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:05:00+00:00'), 0
        )
        self.assertEqual(
            deliver(self.conn, 'tok', '2026-10-09T11:11:00+00:00'), 1
        )

    def test_un_identifiant_mal_ecrit_est_refuse(self) -> None:
        self.assertIn(
            '17 à 20 chiffres', regler_forum(self.conn, 'tickets', 'owner')
        )
        self.assertEqual(regler_forum(self.conn, '', 'owner'), '')


if __name__ == '__main__':
    unittest.main()
