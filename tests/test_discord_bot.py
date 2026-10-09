#!/usr/bin/env python3
"""Bot Discord : administrateur repris, boutons, fenêtres de saisie.

Scénarios :
- l'administrateur du fichier d'instance devient, une fois, le premier
  administrateur en base ; retiré ensuite, il ne revient pas ;
- un bouton tranche le ticket, est accusé, et les cartes sont mises à
  jour tout de suite ;
- un bouton qui demande un texte ouvre une fenêtre ; la fenêtre envoyée
  est confirmée ;
- une personne qui n'est pas administrateur est refusée ;
- un message libre est ignoré.
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
from serge.discord.bot import Bot  # noqa: E402
from serge.tickets import create_ticket, publish  # noqa: E402
from serge.tickets.admins import admins, remove_admin  # noqa: E402
from serge.tickets.types import ticket_types  # noqa: E402

OWNER = '999988887777666555'
CFG = {'guild_id': '100000000000000001', 'owner_user_id': OWNER}
NOW = '2026-09-09T19:00:00+00:00'


class DiscordBotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _bot(self) -> Bot:
        return Bot(self.conn, {}, dict(CFG), 'tok-fake-40')

    def _ticket(self, kind: str = 'VETO_AMONT') -> str:
        ticket_id = create_ticket(
            self.conn,
            ticket_types(self.conn),
            kind,
            'V',
            {'decision': 'x'},
            now=NOW,
        )
        publish(self.conn, ticket_id)
        return ticket_id

    def _state(self, ticket_id: str) -> str:
        return str(
            self.conn.execute(
                'SELECT state FROM tickets WHERE id=?', (ticket_id,)
            ).fetchone()[0]
        )

    def test_l_administrateur_de_l_instance_est_repris_une_fois(self) -> None:
        self._bot()
        self.assertEqual([a['user_id'] for a in admins(self.conn)], [OWNER])
        remove_admin(self.conn, OWNER, 'owner')
        self._bot()
        self.assertEqual(admins(self.conn), [])

    def test_un_bouton_tranche_et_met_a_jour_les_cartes(self) -> None:
        bot = self._bot()
        ticket_id = self._ticket()
        interaction = {
            'id': '9001',
            'token': 'tok-ia-1',
            'type': 3,
            'user': {'id': OWNER},
            'data': {'custom_id': f't:{ticket_id}:approuver'},
        }
        with (
            mock.patch('serge.discord.bot.interaction_callback') as acked,
            mock.patch('serge.discord.bot.deliver') as delivered,
        ):
            bot.on_interaction(interaction)
        self.assertEqual(self._state(ticket_id), 'APPROVED')
        self.assertEqual(acked.call_args[0][2], {'type': 6})
        delivered.assert_called_once()

    def test_un_texte_ouvre_une_fenetre_puis_est_confirme(self) -> None:
        bot = self._bot()
        ticket_id = self._ticket('QNA')
        with mock.patch('serge.discord.bot.interaction_callback') as acked:
            bot.on_interaction(
                {
                    'id': '9002',
                    'token': 'tok-ia-2',
                    'type': 3,
                    'user': {'id': OWNER},
                    'data': {'custom_id': f't:{ticket_id}:reponse_libre'},
                }
            )
        reponse = acked.call_args[0][2]
        self.assertEqual(reponse['type'], 9)
        self.assertEqual(
            reponse['data']['custom_id'], f'm:{ticket_id}:reponse_libre'
        )
        with (
            mock.patch('serge.discord.bot.interaction_callback') as acked,
            mock.patch('serge.discord.bot.deliver'),
        ):
            bot.on_interaction(
                {
                    'id': '9003',
                    'token': 'tok-ia-3',
                    'type': 5,
                    'user': {'id': OWNER},
                    'data': {
                        'custom_id': f'm:{ticket_id}:reponse_libre',
                        'components': [
                            {
                                'type': 1,
                                'components': [
                                    {
                                        'type': 4,
                                        'custom_id': 'texte',
                                        'value': 'Par e-mail',
                                    }
                                ],
                            }
                        ],
                    },
                }
            )
        self.assertEqual(self._state(ticket_id), 'APPROVED')
        confirme = acked.call_args[0][2]
        self.assertEqual(
            (confirme['type'], confirme['data']['flags']), (4, 64)
        )

    def test_une_personne_qui_n_est_pas_administrateur_est_refusee(
        self,
    ) -> None:
        bot = self._bot()
        ticket_id = self._ticket()
        with mock.patch('serge.discord.bot.interaction_callback') as acked:
            bot.on_interaction(
                {
                    'id': '9004',
                    'token': 'tok-ia-4',
                    'type': 3,
                    'user': {'id': '123456789012345678'},
                    'data': {'custom_id': f't:{ticket_id}:approuver'},
                }
            )
        self.assertEqual(self._state(ticket_id), 'OPEN')
        self.assertIn(
            'administrateurs', acked.call_args[0][2]['data']['content']
        )

    def test_un_message_libre_est_ignore(self) -> None:
        bot = self._bot()
        with mock.patch('serge.discord.bot.route_interaction') as routed:
            bot.on_gateway_event(
                'MESSAGE_CREATE', {'content': 'salut', 'author': {'id': OWNER}}
            )
        routed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
