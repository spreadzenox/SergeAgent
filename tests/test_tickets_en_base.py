#!/usr/bin/env python3
"""Les types de tickets et les administrateurs Discord en base (Q85, Q86).

Scénarios :
- les types viennent du fichier de départ ; un type déjà en base n'est
  jamais écrasé au démarrage ;
- un ticket prend le délai de son type en base ;
- un changement refusé (délai, boutons) ne laisse rien à moitié fait ;
- un type retiré du fichier (section ``deleted``) est effacé d'une instance
  en place ; un ticket ouvert sous ce nom reste lisible, sans boutons ;
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
        self.assertEqual(types['PLAN_POC']['expiry_minutes'], 48 * 60)
        self.assertIsNone(types['FYI']['expiry_minutes'])
        self.assertEqual(types['GUICHET']['expiry_minutes'], 10)
        self.assertIn('a_corriger', types['PLAN_POC']['buttons'])
        self.assertEqual(
            set_ticket_type(self.conn, 'PLAN_POC', 'clem', expiry_minutes=120),
            '',
        )
        ensure_ticket_types(self.conn)
        self.assertEqual(
            ticket_types(self.conn)['PLAN_POC']['expiry_minutes'], 120
        )

    def test_une_instance_en_place_recoit_les_changements_des_types(
        self,
    ) -> None:
        """Une instance du lot 10 : la demande sans en-tête ni réponse, le
        plan sans « En bref ». Au démarrage, les types changent, une seule
        fois ; des boutons changés dans Mission Control sont gardés."""
        import json

        c = self.conn
        c.execute(
            'UPDATE ticket_types SET buttons_json=\'["discuter_fil"]\','
            " spec_json=json_set(spec_json, '$.fields',"
            ' json(\'["demande","contexte","point_llm"]\'))'
            " WHERE id='REQUESTED'"
        )
        c.execute(
            'UPDATE ticket_types SET buttons_json=\'["valider"]\''
            " WHERE id='PLAN_PRODUIT'"
        )
        c.execute(
            "DELETE FROM pipeline_changes WHERE id LIKE 'ticket-types.%'"
        )
        ensure_ticket_types(c)
        types = ticket_types(c)
        self.assertEqual(
            types['REQUESTED']['buttons'],
            ['reponse_libre', 'faire_sans', 'discuter_fil'],
        )
        self.assertEqual(types['REQUESTED']['fields'][0], 'en_bref')
        self.assertEqual(types['PLAN_PRODUIT']['buttons'], ['valider'])
        self.assertEqual(types['PLAN_PRODUIT']['fields'][0], 'En bref')
        resultat = dict(
            c.execute(
                'SELECT id, result FROM pipeline_changes'
                " WHERE id='ticket-types.demande_bloquante'"
            ).fetchall()
        )
        self.assertIn(
            'buttons changé', resultat['ticket-types.demande_bloquante']
        )
        # Une seule fois : un bouton retiré ensuite ne revient pas.
        set_ticket_type(c, 'REQUESTED', 'clem', buttons=['faire_sans'])
        ensure_ticket_types(c)
        self.assertEqual(
            ticket_types(c)['REQUESTED']['buttons'], ['faire_sans']
        )
        self.assertTrue(
            json.loads(
                c.execute(
                    "SELECT spec_json FROM ticket_types WHERE id='CONVERSATION'"
                ).fetchone()[0]
            )['contenu'][2]['fin']
        )

    def test_une_instance_en_place_perd_les_types_retires(self) -> None:
        """Une instance d'avant le nettoyage : « Mémoire » et « Question »
        sont en base, et un vieux ticket « Question » est ouvert. Au
        démarrage, ces types sont effacés ; les autres ne bougent pas, le
        vieux ticket reste lisible, sans boutons, et on ne peut plus en
        ouvrir de pareil."""
        from serge.mc.proj_tickets import project_carte
        from serge.registry import load_ticket_types_deleted
        from serge.tickets import TicketError, publish

        c = self.conn
        retires = load_ticket_types_deleted()
        self.assertIn('MEMORY', retires)
        self.assertEqual(set(retires) & set(ticket_types(c)), set())
        for nom in ('MEMORY', 'QNA'):
            c.execute(
                'INSERT INTO ticket_types(id, expiry_minutes, default_detail,'
                ' buttons_json, spec_json, updated_by, updated_at)'
                ' VALUES(?,?,?,?,?,?,?)',
                (
                    nom,
                    4320,
                    '',
                    '["reponse_libre", "discuter"]',
                    '{"fields": ["question"], "default": "rien"}',
                    'ticket-types.yaml',
                    NOW,
                ),
            )
        vieux = create_ticket(
            c,
            ticket_types(c),
            'QNA',
            'Q',
            {'question': 'Quel prix ?'},
            now=NOW,
        )
        publish(c, vieux)
        set_ticket_type(c, 'PLAN_POC', 'clem', expiry_minutes=120)
        avant = len(ticket_types(c))
        ensure_ticket_types(c)
        types = ticket_types(c)
        self.assertEqual(len(types), avant - 2)
        self.assertNotIn('MEMORY', types)
        self.assertNotIn('QNA', types)
        self.assertEqual(types['PLAN_POC']['expiry_minutes'], 120)
        carte = project_carte(c, vieux)
        assert carte is not None
        self.assertEqual(carte['ticket']['type'], 'QNA')
        self.assertEqual(carte['ticket']['etat'], 'OPEN')
        self.assertEqual(carte['boutons'], [])
        with self.assertRaises(TicketError):
            create_ticket(c, types, 'QNA', 'Q', {}, now=NOW)

    def test_un_ticket_prend_le_delai_de_son_type(self) -> None:
        set_ticket_type(self.conn, 'PLAN_POC', 'clem', expiry_minutes=120)
        ticket_id = create_ticket(
            self.conn, ticket_types(self.conn), 'PLAN_POC', 'Q', {}, now=NOW
        )
        expiry = self.conn.execute(
            'SELECT expiry_at FROM tickets WHERE id=?', (ticket_id,)
        ).fetchone()[0]
        self.assertEqual(
            datetime.fromisoformat(expiry) - datetime.fromisoformat(NOW),
            timedelta(minutes=120),
        )
        set_ticket_type(self.conn, 'PLAN_POC', 'clem', expiry_minutes=None)
        sans = create_ticket(
            self.conn, ticket_types(self.conn), 'PLAN_POC', 'Q', {}, now=NOW
        )
        self.assertEqual(
            self.conn.execute(
                'SELECT expiry_at FROM tickets WHERE id=?', (sans,)
            ).fetchone()[0],
            '',
        )

    def test_un_changement_refuse_ne_laisse_rien(self) -> None:
        avant = ticket_types(self.conn)['PLAN_POC']
        for changement in (
            {'expiry_minutes': 0},
            {'expiry_minutes': 120, 'buttons': ['lancer_fusee']},
            {'expiry_minutes': 120, 'buttons': []},
        ):
            self.assertNotEqual(
                set_ticket_type(self.conn, 'PLAN_POC', 'clem', **changement),
                '',
                changement,
            )
        self.assertEqual(ticket_types(self.conn)['PLAN_POC'], avant)
        self.assertIn('inconnu', set_ticket_type(self.conn, 'NOPE', 'clem'))
        self.assertEqual(
            set_ticket_type(
                self.conn,
                'PLAN_POC',
                'clem',
                default_detail='Serge tranche seul.',
                buttons=['approuver', 'discuter'],
            ),
            '',
        )
        apres = ticket_types(self.conn)['PLAN_POC']
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
