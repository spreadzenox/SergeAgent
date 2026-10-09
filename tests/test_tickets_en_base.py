#!/usr/bin/env python3
"""Les types de tickets et les administrateurs Discord en base (Q85, Q86).

Scénarios :
- les types viennent du fichier de départ ; un type déjà en base n'est
  jamais écrasé au démarrage ;
- un ticket prend le délai de son type en base ;
- un changement refusé (délai, boutons) ne laisse rien à moitié fait ;
- un administrateur s'ajoute par un identifiant Discord valide, une fois.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.tickets import create_ticket  # noqa: E402
from serge.tickets.admins import add_admin, admins, remove_admin  # noqa: E402
from serge.tickets.types import (  # noqa: E402
    ensure_ticket_types,
    set_ticket_type,
    ticket_types,
)

NOW = '2026-10-09T10:00:00+00:00'


class TicketTypesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_les_types_viennent_du_fichier_sans_etre_ecrases(self) -> None:
        types = ticket_types(self.conn)
        self.assertEqual(types['QNA']['expiry_minutes'], 72 * 60)
        self.assertIsNone(types['FYI']['expiry_minutes'])
        self.assertEqual(types['GUICHET']['expiry_minutes'], 10)
        self.assertIn('choix_qcm', types['QNA']['buttons'])
        self.assertEqual(
            set_ticket_type(self.conn, 'QNA', 'clem', expiry_minutes=120), ''
        )
        ensure_ticket_types(self.conn)
        self.assertEqual(ticket_types(self.conn)['QNA']['expiry_minutes'], 120)

    def test_un_ticket_prend_le_delai_de_son_type(self) -> None:
        set_ticket_type(self.conn, 'QNA', 'clem', expiry_minutes=120)
        ticket_id = create_ticket(
            self.conn, ticket_types(self.conn), 'QNA', 'Q', {}, now=NOW
        )
        expiry = self.conn.execute(
            'SELECT expiry_at FROM tickets WHERE id=?', (ticket_id,)
        ).fetchone()[0]
        self.assertEqual(
            datetime.fromisoformat(expiry) - datetime.fromisoformat(NOW),
            timedelta(minutes=120),
        )
        set_ticket_type(self.conn, 'QNA', 'clem', expiry_minutes=None)
        sans = create_ticket(
            self.conn, ticket_types(self.conn), 'QNA', 'Q', {}, now=NOW
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT expiry_at FROM tickets WHERE id=?', (sans,)
            ).fetchone()[0],
            '',
        )

    def test_un_changement_refuse_ne_laisse_rien(self) -> None:
        avant = ticket_types(self.conn)['QNA']
        for changement in (
            {'expiry_minutes': 0},
            {'expiry_minutes': 120, 'buttons': ['lancer_fusee']},
            {'expiry_minutes': 120, 'buttons': []},
        ):
            self.assertNotEqual(
                set_ticket_type(self.conn, 'QNA', 'clem', **changement),
                '',
                changement,
            )
        self.assertEqual(ticket_types(self.conn)['QNA'], avant)
        self.assertIn('inconnu', set_ticket_type(self.conn, 'NOPE', 'clem'))
        self.assertEqual(
            set_ticket_type(
                self.conn,
                'QNA',
                'clem',
                default_detail='Serge tranche seul.',
                buttons=['approuver', 'discuter'],
            ),
            '',
        )
        apres = ticket_types(self.conn)['QNA']
        self.assertEqual(apres['buttons'], ['approuver', 'discuter'])
        self.assertEqual(apres['default_detail'], 'Serge tranche seul.')


class AdminsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_un_administrateur_par_identifiant_discord(self) -> None:
        self.assertIn(
            '17 à 20 chiffres', add_admin(self.conn, '12', 'X', 'owner')
        )
        self.assertIn(
            '17 à 20 chiffres', add_admin(self.conn, '@clem', 'X', 'owner')
        )
        self.assertEqual(
            add_admin(self.conn, '111122223333444455', 'Clem', 'owner'), ''
        )
        self.assertEqual(
            add_admin(self.conn, '111122223333444455', 'Clem', 'owner'),
            'déjà administrateur',
        )
        self.assertEqual(
            [(a['user_id'], a['name']) for a in admins(self.conn)],
            [('111122223333444455', 'Clem')],
        )
        self.assertEqual(
            remove_admin(self.conn, '111122223333444455', 'owner'), ''
        )
        self.assertEqual(admins(self.conn), [])
        self.assertEqual(
            remove_admin(self.conn, '111122223333444455', 'owner'),
            'pas administrateur',
        )


if __name__ == '__main__':
    unittest.main()
