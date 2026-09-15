#!/usr/bin/env python3
"""Verrou SHA : fichier == semence ; chaque point YAML a une ligne."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.code_lock import verifier_verrous  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.llm_registre import POINT_LOCKS  # noqa: E402
from serge.registry import load_llm_points  # noqa: E402


class CodeLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_sha_aligne_sur_les_fichiers(self) -> None:
        self.assertEqual(verifier_verrous(self.conn, ROOT), [])

    def test_chaque_point_yaml_est_en_base(self) -> None:
        yaml_ids = set(load_llm_points())
        self.assertEqual(yaml_ids, set(POINT_LOCKS))
        rows = {
            str(r[0]) for r in self.conn.execute('SELECT id FROM llm_points')
        }
        self.assertEqual(yaml_ids, rows)

    def test_jonction_couche5_et_tools_yaml(self) -> None:
        usage = {
            str(r[0]): str(r[1])
            for r in self.conn.execute(
                'SELECT tool_id, usage FROM llm_point_tools'
                " WHERE point_id='cluster_demand'"
            )
        }
        self.assertEqual(usage['memory_search'], 'autorise')
        voix = {
            str(r[0]): str(r[1])
            for r in self.conn.execute(
                'SELECT tool_id, usage FROM llm_point_tools'
                " WHERE point_id='voice_dialog'"
            )
        }
        self.assertEqual(voix['memory_search'], 'interdit')
        self.assertEqual(voix['agenda'], 'declare')
        self.assertEqual(voix['catalogue'], 'declare')
        self.assertEqual(voix['fiches'], 'declare')
        self.assertEqual(voix['identity_basique'], 'declare')

    def test_sha_change_hurle(self) -> None:
        self.conn.execute(
            "UPDATE tools SET code_sha=? WHERE id='memory_search'",
            ('0' * 64,),
        )
        erreurs = verifier_verrous(self.conn, ROOT)
        self.assertTrue(any('memory_search' in e for e in erreurs))


if __name__ == '__main__':
    unittest.main()
