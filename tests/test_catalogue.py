#!/usr/bin/env python3
"""Catalogue : graphe d’architecture complet et relié dès le boot."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.catalogue import (  # noqa: E402
    CatalogueError,
    objets_de_etape,
    verifier_catalogue,
)
from serge.db.boot import init_schema  # noqa: E402
from serge.etapes import ETAPE_IDS  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402


class CatalogueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_instance_vide_a_le_graphe(self) -> None:
        verifier_catalogue(self.conn)
        pre = objets_de_etape(self.conn, 'pre_prospection')
        self.assertIn('cluster_demand', [r['id'] for r in pre['llm']])
        self.assertIn('cluster_listen', [r['id'] for r in pre['tech']])
        self.assertIn('listen.collect', pre['kinds'])
        for ident in ETAPE_IDS:
            objets_de_etape(self.conn, ident)

    def test_jonction_orpheline_refusee(self) -> None:
        self.conn.execute(
            'INSERT INTO llm_point_tools(point_id, tool_id, usage)'
            " VALUES('ghost','nope','declare')"
        )
        with self.assertRaises(CatalogueError):
            verifier_catalogue(self.conn)

    def test_jonction_canal_orpheline_refusee(self) -> None:
        self.conn.execute(
            'INSERT INTO brique_canaux(canal_id, brique_kind, brique_id)'
            " VALUES('email','llm','ghost')"
        )
        with self.assertRaises(CatalogueError):
            verifier_catalogue(self.conn)

    def test_fiche_etape_montre_tech(self) -> None:
        fiche = project_objet(self.conn, 'etape', 'pre_prospection')
        assert fiche is not None
        self.assertEqual(fiche['titre'], 'Pré-prospection')
        titres = [c['titre'] for c in fiche['cadres']]
        self.assertIn('Invocations techniques', titres)
        self.assertTrue(
            any(c['k'] == 'Dernière modification' for c in fiche['champs'])
        )
        tech = project_objet(self.conn, 'tech', 'cluster_listen')
        assert tech is not None
        self.assertEqual(tech['type'], 'tech')
        self.assertEqual(tech['champs'][0]['v'], 'pre_prospection')

    def test_invocation_retiree_du_code_disparait_de_la_base(self) -> None:
        from serge.llm_registre import ensure_llm_points

        self.conn.execute(
            "INSERT INTO llm_points(id, etape_id, titre) VALUES('ancien','','X')"
        )
        self.conn.execute(
            'INSERT INTO llm_point_tools(point_id, tool_id, usage)'
            " VALUES('ancien','memory_search','autorise')"
        )
        ensure_llm_points(self.conn)
        restes = (
            self.conn.execute(
                "SELECT COUNT(*) FROM llm_points WHERE id='ancien'"
            ).fetchone()[0]
            + self.conn.execute(
                "SELECT COUNT(*) FROM llm_point_tools WHERE point_id='ancien'"
            ).fetchone()[0]
        )
        self.assertEqual(restes, 0)


if __name__ == '__main__':
    unittest.main()
