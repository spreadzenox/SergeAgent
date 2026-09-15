#!/usr/bin/env python3
"""Invocations techniques : semence, kind fermé, rattachement à une étape."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.db.schema import SCHEMA_VERSION  # noqa: E402
from serge.outils import outil_peut_invoquer  # noqa: E402
from serge.tech_registre import (  # noqa: E402
    TechError,
    ensure_tech_invocations,
    tech_par_etape,
)


class TechRegistreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_semence_rattachee(self) -> None:
        self.assertEqual(SCHEMA_VERSION, 11)
        rows = tech_par_etape(self.conn, 'pre_prospection')
        ids = [r['id'] for r in rows]
        self.assertIn('cluster_listen', ids)
        self.assertEqual(rows[0]['kind'], 'cluster')
        choix = tech_par_etape(self.conn, 'choix_venture')
        self.assertIn('select_pre_venture', [r['id'] for r in choix])

    def test_kind_inconnu_refuse(self) -> None:
        self.conn.execute('DELETE FROM tech_invocations')
        from serge import tech_registre as mod

        ancien = mod.SEED
        mod.SEED = (('x', 'caisse', 'pas-un-kind', '', '', 'X', ''),)
        self.addCleanup(setattr, mod, 'SEED', ancien)
        with self.assertRaises(TechError):
            ensure_tech_invocations(self.conn)

    def test_agent_ne_chaine_pas_un_agent(self) -> None:
        self.assertFalse(outil_peut_invoquer('agent', 'agent'))
        self.assertTrue(outil_peut_invoquer('llm', 'agent'))
        self.assertTrue(outil_peut_invoquer('deterministe', 'web'))


if __name__ == '__main__':
    unittest.main()
