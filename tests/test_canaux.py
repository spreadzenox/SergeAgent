#!/usr/bin/env python3
"""Canaux : semence, jonction n-n, fiche MC, refus."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.canaux import (  # noqa: E402
    CanalError,
    briques_du_canal,
    canaux_de_etape,
    ensure_canaux,
    fiche_canal,
)
from serge.catalogue import CatalogueError, verifier_catalogue  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402


class CanauxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_semence_ecriture_seulement(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 12)
        ids = {str(r[0]) for r in self.conn.execute('SELECT id FROM canaux')}
        self.assertEqual(ids, {'email', 'voice'})
        self.assertNotIn('discord', ids)
        self.assertNotIn('linkedin', ids)
        email = briques_du_canal(self.conn, 'email')
        self.assertIn(
            ('llm', 'fill_slots'), [(b['kind'], b['id']) for b in email]
        )
        self.assertIn(
            'email', [c['id'] for c in canaux_de_etape(self.conn, 'caisse')]
        )

    def test_fiche_et_etape(self) -> None:
        fiche = project_objet(self.conn, 'canal', 'email')
        assert fiche is not None
        self.assertEqual(fiche['type'], 'canal')
        self.assertEqual(fiche['titre'], 'E-mail')
        ids = [
            lien['id']
            for c in fiche['cadres']
            if c['titre'].startswith('Briques')
            for lien in c['liens']
        ]
        self.assertIn('fill_slots', ids)
        self.assertIn('dunning', ids)
        etape = project_objet(self.conn, 'etape', 'prospection_light')
        assert etape is not None
        titres = [c['titre'] for c in etape['cadres']]
        self.assertIn('Canaux', titres)
        llm = project_objet(self.conn, 'llm', 'fill_slots')
        assert llm is not None
        canaux = next(c for c in llm['cadres'] if c['titre'] == 'Canaux')
        self.assertEqual([lien['id'] for lien in canaux['liens']], ['email'])

    def test_kind_inconnu_refuse(self) -> None:
        from serge import canaux as mod

        ancien = mod.JONCTIONS
        mod.JONCTIONS = (('email', 'agent', 'x'),)
        self.addCleanup(setattr, mod, 'JONCTIONS', ancien)
        with self.assertRaises(CanalError):
            ensure_canaux(self.conn)

    def test_jonction_orpheline_refusee(self) -> None:
        self.conn.execute(
            'INSERT INTO brique_canaux(canal_id, brique_kind, brique_id)'
            " VALUES('email','llm','ghost')"
        )
        with self.assertRaises(CatalogueError):
            verifier_catalogue(self.conn)

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
