#!/usr/bin/env python3
"""La grille de points (lot 9, décision Q84).

Scénarios :
- un prospect compte une fois, pour sa meilleure réaction, tous canaux
  confondus ; un prospect qui écrit plusieurs fois ne gonfle pas le total ;
- un message pas encore traité, ou pas rattaché, ne compte pas ;
- changer le barème recompte le business ;
- chaque réaction de « Traiter une réponse » a sa case du barème, pour
  chaque canal branché : une réaction ou un canal nouveau sans barème est
  refusé ;
- ce qu'un business a dépensé : le coût réel des modèles de ses tâches
  (les jetons sans coût à part) et ses minutes d'appel terminées, au prix
  de la page Policy ; ses points par euro.
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
from serge.funnels.depense import (  # noqa: E402
    depense_business,
    points_par_euro,
    texte_euros,
)
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
                'c1': {
                    'points': 8.0,
                    'canal': 'voice',
                    'reaction': 'intéressé',
                },
                'c2': {
                    'points': 4.0,
                    'canal': 'email',
                    'reaction': 'question',
                },
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

    def _tache(
        self, ident: str, file: str, venture: str, statut: str, fin: str
    ) -> None:
        self.conn.execute(
            'INSERT INTO tasks(id, invocation_id, queue_id, status,'
            ' idempotency_key, created_at, started_at, finished_at)'
            " VALUES(?, 'x', ?, ?, ?, 't', '2026-10-09T10:00:00+00:00', ?)",
            (ident, file, statut, ident, fin),
        )
        self.conn.execute(
            "INSERT INTO task_params(task_id, name, value) VALUES(?, 'venture_id', ?)",
            (ident, venture),
        )

    def test_ce_qu_un_business_a_depense(self) -> None:
        # Deux appels au modèle pour une tâche du business : 1 $ facturé,
        # et un appel sans coût connu ; un appel raté ne coûte rien.
        self._tache('t_ecrire', 'conversations', 'v1', 'done', '')
        for cout, jetons, verdict in (
            (1.0, 500, 'ok'),
            (None, 1000, 'ok'),
            (5.0, 0, 'erreur'),
        ):
            self.conn.execute(
                'INSERT INTO llm_usage(point, tier, tokens_in, tokens_out,'
                ' verdict, cost_usd, task_id, created_at)'
                " VALUES('x', 'mid', ?, 0, ?, ?, 't_ecrire', 't')",
                (jetons, verdict, cout),
            )
        # Un appel de trois minutes ; un appel coupé par un redémarrage du
        # pont ne compte pas ; un appel d'un autre business non plus.
        self._tache(
            't_appel', 'voice', 'v1', 'done', '2026-10-09T10:03:00+00:00'
        )
        self._tache(
            't_coupe', 'voice', 'v1', 'failed', '2026-10-09T18:00:00+00:00'
        )
        self._tache(
            't_autre', 'voice', 'v2', 'done', '2026-10-09T10:10:00+00:00'
        )
        depense = depense_business(self.conn, 'v1')
        # 1 $ × 0,9 = 0,90 € ; 3 minutes × 0,10 € = 0,30 €.
        self.assertEqual(
            depense,
            {
                'modeles_eur': 0.9,
                'jetons_sans_cout': 1000,
                'minutes': 3.0,
                'appels_eur': 0.3,
                'total_eur': 1.2,
            },
        )
        # 12 points pour 1,20 € : 10 points par euro.
        self.assertEqual(
            points_par_euro(points_business(self.conn, 'v1'), 1.2), 10.0
        )
        self.assertIsNone(points_par_euro(12.0, 0.0))
        self.assertEqual(texte_euros(1.2), '1,20')

    def test_texte_des_points(self) -> None:
        self.assertEqual(texte_points(8.0), '8')
        self.assertEqual(texte_points(0.5), '0,5')
        self.assertEqual(texte_points(12.5), '12,5')


if __name__ == '__main__':
    unittest.main()
