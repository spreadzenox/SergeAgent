#!/usr/bin/env python3
"""Coupe-circuits : Serge (arrêté par défaut), étape, file, invocation.

Scénario : deux invocations sans LLM, « a » (étape 1, priorité 50) et
« b » (étape 8, priorité 10), ont chacune une tâche prête dans la file des
travaux. On coupe l'un ou l'autre, et on regarde quelle tâche la file
prend.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import (  # noqa: E402
    CoupeError,
    appliquer_coupe,
    etat_coupes,
    heartbeat_marche,
)
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'


def _invocation(ident: str, step: str, priority: int) -> dict:
    return {
        'id': ident,
        'title': ident.upper(),
        'type': 'capability',
        'capability': 'echo',
        'step': step,
        'queue': 'works',
        'priority': priority,
    }


class CoupeCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        sans_pipeline_de_depart(self.conn)
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    _invocation('a', 'pre_prospection', 50),
                    _invocation('b', 'caisse', 10),
                ],
            },
        )
        self.tasks = {
            ident: enqueue_task(self.conn, ident, {'n': ident})
            for ident in ('a', 'b')
        }
        self.conn.commit()

    def test_par_defaut_serge_est_arrete(self) -> None:
        self.assertFalse(heartbeat_marche(self.conn))
        self.assertIsNone(self._next())
        self.assertFalse(etat_coupes(self.conn)['serge'])
        appliquer_coupe(self.conn, 'serge', '', True)
        self.assertTrue(heartbeat_marche(self.conn))
        self.assertEqual(self._next(), self.tasks['a'])

    def _demarrer(self) -> None:
        appliquer_coupe(self.conn, 'serge', '', True)

    def _next(self) -> str | None:
        return process_one(self.conn, 'works', now=NOW)

    def test_serge_arrete_rien_ne_tourne(self) -> None:
        self.conn.execute(
            'INSERT INTO triggers(id, invocation_id, event, every_minutes)'
            " VALUES('toutes_5', 'b', 'every', 5)"
        )
        self._demarrer()
        appliquer_coupe(self.conn, 'serge', '', False)
        self.assertFalse(heartbeat_marche(self.conn))
        self.assertIsNone(self._next())
        creees = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE origin='trigger'"
        ).fetchone()[0]
        self.assertEqual(creees, 0)
        appliquer_coupe(self.conn, 'serge', '', True)
        self.assertEqual(self._next(), self.tasks['a'])

    def test_etape_coupee_laisse_passer_les_autres(self) -> None:
        self._demarrer()
        appliquer_coupe(self.conn, 'etape', 'pre_prospection', False)
        self.assertEqual(self._next(), self.tasks['b'])
        self.assertIsNone(self._next())
        appliquer_coupe(self.conn, 'etape', 'pre_prospection', True)
        self.assertEqual(self._next(), self.tasks['a'])

    def test_file_coupee(self) -> None:
        self._demarrer()
        etat = appliquer_coupe(self.conn, 'file', 'works', False)
        self.assertEqual(
            etat, {'cible': 'file', 'id': 'works', 'marche': False}
        )
        self.assertIsNone(self._next())

    def test_invocation_coupee(self) -> None:
        self._demarrer()
        appliquer_coupe(self.conn, 'invocation', 'a', False)
        self.assertEqual(self._next(), self.tasks['b'])
        self.assertIsNone(self._next())

    def test_cible_ou_id_inconnu_refuse(self) -> None:
        with self.assertRaises(CoupeError):
            appliquer_coupe(self.conn, 'nuage', '', False)
        with self.assertRaises(CoupeError):
            appliquer_coupe(self.conn, 'etape', 'nexiste_pas', False)
        with self.assertRaises(CoupeError):
            appliquer_coupe(self.conn, 'invocation', 'nexiste_pas', False)
        with self.assertRaises(CoupeError):
            appliquer_coupe(self.conn, 'file', 'nexiste_pas', False)

    def test_etat_coupes_defaut_tout_marche(self) -> None:
        data = etat_coupes(self.conn)
        self.assertFalse(data['serge'])
        self.assertEqual(len(data['etapes']), 8)
        self.assertEqual(
            [f['id'] for f in data['files']], ['conversations', 'works']
        )
        self.assertEqual([i['id'] for i in data['invocations']], ['a', 'b'])
        for groupe in ('etapes', 'files', 'invocations'):
            self.assertTrue(all(item['marche'] for item in data[groupe]))


if __name__ == '__main__':
    unittest.main()
