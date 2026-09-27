#!/usr/bin/env python3
"""Santé des comptes : passant, refus par code, capital bas / haut."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.comptes import enregistrer_compte  # noqa: E402
from serge.comptes_sante import (  # noqa: E402
    SanteError,
    autoriser,
    consommer,
    etat,
)
from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402

T0 = '2026-09-15T12:00:00+00:00'
T3 = '2026-09-15T15:00:00+00:00'
POL = {
    'standing': {
        'cout_usage': 0.10,
        'gain_par_heure': 0.10,
        'idle_apres_heures': 1.0,
        'capital_min': 0.20,
        'capital_max': 1.0,
    }
}


class ComptesSanteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.ident = enregistrer_compte(
            self.conn, 'reddit', 'u/serge', 'serge', 'pw'
        )

    def test_schema(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 20)
        have = {
            str(row[1])
            for row in self.conn.execute(
                'PRAGMA table_info(accounts_standing)'
            )
        }
        self.assertIn('last_used_at', have)

    def test_ok_puis_debit(self) -> None:
        vu = etat(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(vu['code'], 'ok')
        self.assertEqual(vu['capital'], 1.0)
        reste = consommer(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertAlmostEqual(reste, 0.90)
        row = self.conn.execute(
            'SELECT capital, last_used_at FROM accounts_standing WHERE id=?',
            (self.ident,),
        ).fetchone()
        self.assertAlmostEqual(row[0], 0.90)
        self.assertEqual(row[1], T0)

    def test_pause_et_insister_refuse(self) -> None:
        self.conn.execute(
            'UPDATE accounts_standing SET cooldown_until=? WHERE id=?',
            ('2026-09-15T18:00:00+00:00', self.ident),
        )
        vu = etat(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(vu['code'], 'pause')
        with self.assertRaises(SanteError) as ctx:
            autoriser(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(ctx.exception.code, 'pause')
        with self.assertRaises(SanteError) as ctx2:
            autoriser(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(ctx2.exception.code, 'pause')

    def test_inactif_et_inconnu(self) -> None:
        self.conn.execute(
            "UPDATE accounts_standing SET status='dead' WHERE id=?",
            (self.ident,),
        )
        with self.assertRaises(SanteError) as ctx:
            autoriser(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(ctx.exception.code, 'inactif')
        with self.assertRaises(SanteError) as ctx2:
            autoriser(self.conn, 's_absent', maintenant=T0, policy=POL)
        self.assertEqual(ctx2.exception.code, 'inconnu')

    def test_capital_trop_bas(self) -> None:
        self.conn.execute(
            'UPDATE accounts_standing SET capital=0.10 WHERE id=?',
            (self.ident,),
        )
        with self.assertRaises(SanteError) as ctx:
            consommer(self.conn, self.ident, maintenant=T0, policy=POL)
        self.assertEqual(ctx.exception.code, 'capital')
        self.assertAlmostEqual(
            self.conn.execute(
                'SELECT capital FROM accounts_standing WHERE id=?',
                (self.ident,),
            ).fetchone()[0],
            0.10,
        )

    def test_repos_remonte_sans_depasser(self) -> None:
        self.conn.execute(
            'UPDATE accounts_standing SET capital=0.50, last_used_at=?'
            ' WHERE id=?',
            (T0, self.ident),
        )
        vu = etat(self.conn, self.ident, maintenant=T3, policy=POL)
        self.assertEqual(vu['code'], 'ok')
        self.assertAlmostEqual(vu['capital'], 0.80)
        self.conn.execute(
            'UPDATE accounts_standing SET capital=0.95, last_used_at=?'
            ' WHERE id=?',
            (T0, self.ident),
        )
        haut = etat(self.conn, self.ident, maintenant=T3, policy=POL)
        self.assertAlmostEqual(haut['capital'], 1.0)
