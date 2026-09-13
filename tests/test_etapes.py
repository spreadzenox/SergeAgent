#!/usr/bin/env python3
"""pipeline_steps : semence, interrupteur, kinds coupés."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.etapes import (  # noqa: E402
    EtapeError,
    etats_etapes,
    kinds_coupes,
    set_etape_marche,
)


class EtapesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_semence_sept_etapes_en_marche(self) -> None:
        etats = etats_etapes(self.conn)
        self.assertEqual(
            list(etats),
            [
                'ecoute',
                'hypothese',
                'test',
                'qualif',
                'conversation',
                'intent',
                'caisse',
            ],
        )
        self.assertTrue(all(e['marche'] for e in etats.values()))
        self.assertIn('listen.collect', etats['ecoute']['kinds'])
        self.assertIn('email.send', etats['test']['kinds'])
        self.assertEqual(kinds_coupes(self.conn), frozenset())

    def test_couper_ecoute_bloque_ses_kinds(self) -> None:
        set_etape_marche(self.conn, 'ecoute', False)
        self.assertFalse(etats_etapes(self.conn)['ecoute']['marche'])
        self.assertEqual(
            kinds_coupes(self.conn),
            frozenset({'listen.collect', 'listen.cluster'}),
        )
        set_etape_marche(self.conn, 'ecoute', True)
        self.assertEqual(kinds_coupes(self.conn), frozenset())

    def test_inconnue_refuse(self) -> None:
        with self.assertRaises(EtapeError):
            set_etape_marche(self.conn, 'nexistepas', False)

    def test_kinds_mis_a_jour_sans_toucher_enabled(self) -> None:
        set_etape_marche(self.conn, 'test', False)
        init_schema(self.conn)
        self.assertFalse(etats_etapes(self.conn)['test']['marche'])
        self.assertIn('voice.send', etats_etapes(self.conn)['test']['kinds'])


if __name__ == '__main__':
    unittest.main()
