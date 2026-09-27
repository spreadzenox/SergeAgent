#!/usr/bin/env python3
"""pipeline_steps : 8 sacs, interrupteur, coupe par etape_id."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.etapes import (  # noqa: E402
    ETAPE_IDS,
    EtapeError,
    etapes_coupees,
    etats_etapes,
    set_etape_marche,
)


class EtapesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_semence_huit_etapes_en_marche(self) -> None:
        etats = etats_etapes(self.conn)
        self.assertEqual(list(etats), list(ETAPE_IDS))
        self.assertTrue(all(e['marche'] for e in etats.values()))
        self.assertEqual(
            [e['rang'] for e in etats.values()], list(range(len(ETAPE_IDS)))
        )
        self.assertEqual(etapes_coupees(self.conn), frozenset())

    def test_couper_pre_prospection(self) -> None:
        set_etape_marche(self.conn, 'pre_prospection', False)
        self.assertFalse(etats_etapes(self.conn)['pre_prospection']['marche'])
        self.assertEqual(
            etapes_coupees(self.conn), frozenset({'pre_prospection'})
        )
        set_etape_marche(self.conn, 'pre_prospection', True)
        self.assertEqual(etapes_coupees(self.conn), frozenset())

    def test_inconnue_refuse(self) -> None:
        with self.assertRaises(EtapeError):
            set_etape_marche(self.conn, 'nexistepas', False)

    def test_redemarrer_ne_touche_pas_l_interrupteur(self) -> None:
        set_etape_marche(self.conn, 'prospection_light', False)
        init_schema(self.conn)
        self.assertFalse(
            etats_etapes(self.conn)['prospection_light']['marche']
        )


if __name__ == '__main__':
    unittest.main()
