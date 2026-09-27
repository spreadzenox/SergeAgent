#!/usr/bin/env python3
"""Canaux : semence, fiche MC, retrait d'un canal inconnu."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.canaux import CanalError, ensure_canaux, fiche_canal  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402


class CanauxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_semence_ecriture_seulement(self) -> None:
        ids = {str(r[0]) for r in self.conn.execute('SELECT id FROM canaux')}
        self.assertEqual(ids, {'email', 'voice'})

    def test_fiche(self) -> None:
        fiche = project_objet(self.conn, 'canal', 'email')
        assert fiche is not None
        self.assertEqual(fiche['type'], 'canal')
        self.assertEqual(fiche['titre'], 'E-mail')
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(champs['État'], 'prevu')
        self.assertEqual(champs['Fichier'], 'serge/channels/email_smtp.py')
        self.assertIn('lot 8', fiche['cadres'][0]['todo'])

    def test_etat_inconnu_refuse(self) -> None:
        from serge import canaux as mod

        ancien = mod.SEED
        mod.SEED = (('email', 'E-mail', '', '', 'cassé'),)
        self.addCleanup(setattr, mod, 'SEED', ancien)
        with self.assertRaises(CanalError):
            ensure_canaux(self.conn)

    def test_fiche_absente(self) -> None:
        self.assertIsNone(fiche_canal(self.conn, 'linkedin'))
        self.assertIsNone(fiche_canal(self.conn, 'discord'))

    def test_retire_canal_owner(self) -> None:
        self.conn.execute(
            'INSERT INTO canaux(id, titre, doc_md, etat)'
            " VALUES('discord','Discord','owner','branche')"
        )
        ensure_canaux(self.conn)
        ids = {str(r[0]) for r in self.conn.execute('SELECT id FROM canaux')}
        self.assertNotIn('discord', ids)


if __name__ == '__main__':
    unittest.main()
