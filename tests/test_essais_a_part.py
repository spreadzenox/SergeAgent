#!/usr/bin/env python3
"""Les business d'essai sont à part (lot 12, décisions Q98 et Q99).

Un business d'essai est marqué (``ventures.trial``) : c'est le couloir
d'essai qui le marque (tests/test_couloir_essai.py, test_essai_total.py).
Ici, les places et la migration.

Scénarios :
- un business d'essai en test ne prend pas de place : un vrai business
  peut encore être choisi, et un essai n'est jamais refusé ;
- une base du lot 11 : au démarrage, ses business d'essai sont marqués (le
  business de « Lancer un essai », la calculatrice d'un bout en bout), pas
  les vrais.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.migrate import MIGRATIONS, apply_pending  # noqa: E402
from serge.interpreter.rules import quota_refusal, quota_usage  # noqa: E402

MAINTENANT = '2026-11-16T18:00:00+00:00'


def _business(conn: sqlite3.Connection, nom: str, statut: str, **plus) -> None:
    colonnes = {'id': f'ven_{nom}', 'name': nom, 'lifecycle': statut, **plus}
    conn.execute(
        f'INSERT INTO ventures({", ".join(colonnes)}, created_at, updated_at)'
        f' VALUES({", ".join("?" * len(colonnes))}, ?, ?)',
        (*colonnes.values(), MAINTENANT, MAINTENANT),
    )


class PlacesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.execute(
            "UPDATE triggers SET enabled=0 WHERE event<>'button'"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()

    def _places(self) -> tuple[int, int]:
        usage = quota_usage(self.conn, 'places_de_test')
        assert usage is not None
        return usage[0], usage[1]

    def test_un_essai_ne_prend_pas_la_place_d_un_vrai_business(self) -> None:
        _business(self.conn, 'calculatrice', 'SMOKE_READY', trial=1)
        _business(self.conn, 'devis', 'POC_SELECTED')
        _business(self.conn, 'paie', 'POC_SELECTED')
        self.assertEqual(self._places(), (2, 3))
        choisir = {'lifecycle': 'POC_SELECTED'}
        # Un troisième vrai business entre ; le quatrième est refusé.
        self.assertEqual(
            quota_refusal(self.conn, 'ventures', choisir, None), ''
        )
        _business(self.conn, 'stock', 'POC_SELECTED')
        self.assertIn(
            'places_de_test',
            quota_refusal(self.conn, 'ventures', choisir, None),
        )
        # Un essai, lui, n'est jamais refusé : créé comme essai, ou déjà
        # marqué quand son statut change.
        self.assertEqual(
            quota_refusal(
                self.conn, 'ventures', {**choisir, 'trial': 1}, None
            ),
            '',
        )
        self.assertEqual(
            quota_refusal(
                self.conn,
                'ventures',
                choisir,
                {'lifecycle': 'CANDIDATE', 'trial': 1},
            ),
            '',
        )


class BaseDuLot11Tests(unittest.TestCase):
    def test_les_essais_deja_en_base_sont_marques(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        apply_pending(conn, [m for m in MIGRATIONS if m[0] <= 51], head=51)
        _business(conn, 'devis_vocal', 'TEST')
        _business(
            conn,
            'calculatrice',
            'PRODUCT_READY',
            choice_reason='Essai de bout en bout du produit fini depuis'
            ' Mission Control.',
        )
        _business(
            conn,
            'paie',
            'POC_SELECTED',
            choice_reason='Douze artisans demandent la même chose.',
        )
        apply_pending(conn, MIGRATIONS)
        marques = dict(conn.execute('SELECT name, trial FROM ventures'))
        self.assertEqual(
            marques, {'devis_vocal': 1, 'calculatrice': 1, 'paie': 0}
        )


if __name__ == '__main__':
    unittest.main()
