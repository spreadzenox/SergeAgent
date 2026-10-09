#!/usr/bin/env python3
"""La grille de points (lot 9, décision Q84).

Scénarios :
- un prospect compte une fois, pour sa meilleure réaction, tous canaux
  confondus ; un prospect qui écrit plusieurs fois ne gonfle pas le total ;
- un message pas encore traité, ou pas rattaché, ne compte pas ;
- changer le barème recompte le business ;
- chaque réaction de « Traiter une réponse » a sa case du barème, pour
  chaque canal branché : une réaction ou un canal nouveau sans barème est
  refusé.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.channels.adapters import ADAPTERS  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.funnels.points import (  # noqa: E402
    bareme,
    points_business,
    points_contact,
    points_prospects,
    texte_points,
)
from serge.policy_store import set_setting  # noqa: E402


class PointsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        for venture in ('v1', 'v2'):
            self.conn.execute(
                'INSERT INTO ventures(id, name, lifecycle, created_at,'
                " updated_at) VALUES(?, ?, 'TEST', 't', 't')",
                (venture, venture),
            )
        for contact, venture in (
            ('c1', 'v1'),
            ('c2', 'v1'),
            ('c3', 'v1'),
            ('c4', 'v2'),
        ):
            self.conn.execute(
                'INSERT INTO contacts(id, venture_id, display, created_at,'
                " updated_at) VALUES(?, ?, ?, 't', 't')",
                (contact, venture, contact),
            )
        recus = [
            # c1 pose une question par e-mail, puis se dit intéressé au
            # téléphone : il compte pour l'appel (8).
            ('c1', 'v1', 'email', 'attached', 'question'),
            ('c1', 'v1', 'voice', 'attached', 'intéressé'),
            # c2 écrit trois fois : il compte une fois, pour sa question.
            ('c2', 'v1', 'email', 'attached', 'refus'),
            ('c2', 'v1', 'email', 'attached', 'question'),
            ('c2', 'v1', 'email', 'attached', 'question'),
            # c3 : une absence, 0 point, mais il a réagi.
            ('c3', 'v1', 'email', 'attached', 'absence'),
            # Pas encore traité, ou pas rattaché : ne compte pas.
            ('c3', 'v1', 'email', 'attached', ''),
            ('', 'v1', 'email', 'unattached', 'rendez-vous'),
            # Un autre business.
            ('c4', 'v2', 'email', 'attached', 'rendez-vous'),
        ]
        for n, (contact, venture, canal, statut, reaction) in enumerate(recus):
            self.conn.execute(
                'INSERT INTO inbound_events(id, contact_id, venture_id,'
                ' channel, status, reaction, received_at)'
                ' VALUES(?, ?, ?, ?, ?, ?, ?)',
                (
                    f'i{n}',
                    contact,
                    venture,
                    canal,
                    statut,
                    reaction,
                    f'2026-10-09T10:{n:02d}:00+00:00',
                ),
            )

    def test_chaque_prospect_compte_pour_sa_meilleure_reaction(self) -> None:
        self.assertEqual(
            points_prospects(self.conn, 'v1'),
            {
                'c1': {'points': 8.0, 'canal': 'voice', 'reaction': 'intéressé'},
                'c2': {'points': 4.0, 'canal': 'email', 'reaction': 'question'},
                'c3': {'points': 0.0, 'canal': 'email', 'reaction': 'absence'},
            },
        )
        self.assertEqual(points_business(self.conn, 'v1'), 12.0)
        self.assertEqual(points_business(self.conn, 'v2'), 10.0)
        self.assertEqual(
            points_contact(self.conn, 'c1'),
            {'points': 8.0, 'canal': 'voice', 'reaction': 'intéressé'},
        )
        self.assertIsNone(points_contact(self.conn, 'inconnu'))

    def test_changer_le_bareme_recompte_le_business(self) -> None:
        self.assertEqual(
            set_setting(self.conn, 'points.email.question', 6, 'clem'), ''
        )
        self.assertEqual(points_business(self.conn, 'v1'), 14.0)
        # Hors bornes : refusé, comme tout réglage de la page Policy.
        self.assertNotEqual(
            set_setting(self.conn, 'points.email.question', 11, 'clem'), ''
        )

    def test_chaque_reaction_a_sa_case_pour_chaque_canal_branche(self) -> None:
        grille = bareme(self.conn)
        reactions = set()
        for (choix,) in self.conn.execute(
            'SELECT choices FROM invocation_output_fields'
            " WHERE path='reaction' AND choices<>''"
        ).fetchall():
            reactions |= {c.strip() for c in str(choix).split(',')}
        self.assertIn('rendez-vous', reactions)
        canaux = {a.id for a in ADAPTERS.values()}
        manquantes = sorted(
            f'{canal}.{reaction}'
            for canal in canaux
            for reaction in reactions
            if (canal, reaction) not in grille
        )
        self.assertEqual(manquantes, [])

    def test_texte_des_points(self) -> None:
        self.assertEqual(texte_points(8.0), '8')
        self.assertEqual(texte_points(0.5), '0,5')
        self.assertEqual(texte_points(12.5), '12,5')


if __name__ == '__main__':
    unittest.main()
