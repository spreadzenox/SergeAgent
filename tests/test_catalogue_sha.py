#!/usr/bin/env python3
"""Catalogue : ajout / suppression / SHA fichiers ≠ base → rouge."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.catalogue_lock import SHA_ATTENDUS  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.objet_sha import (  # noqa: E402
    ids_semence,
    objets_en_base,
    verifier_objets,
)


class CatalogueShaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def test_semence_base_et_verrou_alignes(self) -> None:
        self.assertEqual(ids_semence(), set(SHA_ATTENDUS))
        self.assertEqual(objets_en_base(self.conn), set(SHA_ATTENDUS))
        self.assertEqual(verifier_objets(self.conn, ROOT), [])

    def test_objet_rajoute_hurle(self) -> None:
        self.conn.execute(
            'INSERT INTO tools(id, kind, titre, doc_md)'
            " VALUES('intrus','deterministe','X','')"
        )
        erreurs = verifier_objets(self.conn, ROOT)
        self.assertTrue(any('rajouté' in e and 'intrus' in e for e in erreurs))

    def test_objet_supprime_hurle(self) -> None:
        self.conn.execute("DELETE FROM tools WHERE id='navigateur'")
        erreurs = verifier_objets(self.conn, ROOT)
        self.assertTrue(
            any('supprimé' in e and 'navigateur' in e for e in erreurs)
        )

    def test_sha_fichiers_different_hurle(self) -> None:
        self.conn.execute(
            "UPDATE tools SET files_sha=? WHERE id='memory_search'",
            ('0' * 64,),
        )
        erreurs = verifier_objets(self.conn, ROOT)
        self.assertTrue(
            any('memory_search' in e and 'SHA' in e for e in erreurs)
        )


if __name__ == '__main__':
    unittest.main()
