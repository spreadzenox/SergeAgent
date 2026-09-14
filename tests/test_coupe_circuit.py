#!/usr/bin/env python3
"""Coupe-circuits : heartbeat, kind, étape — passant et refusé."""

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
    set_heartbeat,
    set_kind_marche,
)
from serge.db.boot import init_schema  # noqa: E402
from serge.etapes import set_etape_marche  # noqa: E402
from serge.scheduler import enqueue, next_ready  # noqa: E402


class CoupeCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, lifecycle, schedulable, created_at,'
            " updated_at) VALUES('v1','SCALE',1,'t','t')"
        )
        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def _ready(self, kind: str, key: str, etape_id: str = '') -> None:
        enqueue(
            self.conn,
            kind=kind,
            idempotency_key=key,
            venture_id='v1',
            etape_id=etape_id,
            priority=10,
        )

    def test_heartbeat_coupe_rien_n_est_pret(self) -> None:
        self._ready('email.send', 'k1')
        self.assertIsNotNone(next_ready(self.conn))
        set_heartbeat(self.conn, False)
        self.assertFalse(heartbeat_marche(self.conn))
        self.assertIsNone(next_ready(self.conn))
        set_heartbeat(self.conn, True)
        item = next_ready(self.conn)
        assert item is not None
        self.assertEqual(item['kind'], 'email.send')

    def test_kind_coupe_ignore_ce_kind(self) -> None:
        self._ready('email.send', 'k-mail')
        self._ready('memory.consolidate', 'k-mem')
        set_kind_marche(self.conn, 'email.send', False)
        item = next_ready(self.conn)
        assert item is not None
        self.assertEqual(item['kind'], 'memory.consolidate')
        set_kind_marche(self.conn, 'email.send', True)
        item = next_ready(self.conn)
        assert item is not None
        self.assertEqual(item['kind'], 'email.send')

    def test_kind_coupe_toutes_etapes(self) -> None:
        self._ready('email.send', 'k-l', etape_id='prospection_light')
        self._ready('email.send', 'k-d', etape_id='prospection_lourde')
        set_kind_marche(self.conn, 'email.send', False)
        self.assertIsNone(next_ready(self.conn))

    def test_etape_coupe_laisse_l_autre_kind(self) -> None:
        self._ready('email.send', 'k-mail')
        self._ready('memory.consolidate', 'k-mem')
        set_etape_marche(self.conn, 'prospection_light', False)
        item = next_ready(self.conn)
        assert item is not None
        self.assertEqual(item['kind'], 'memory.consolidate')

    def test_kind_inconnu_refuse(self) -> None:
        with self.assertRaises(CoupeError):
            set_kind_marche(self.conn, 'nexiste.pas', False)

    def test_cible_inconnue_refuse(self) -> None:
        with self.assertRaises(CoupeError):
            appliquer_coupe(self.conn, 'nuage', '', False)

    def test_etat_coupes_defaut_tout_marche(self) -> None:
        data = etat_coupes(self.conn)
        self.assertTrue(data['serge'])
        self.assertTrue(all(e['marche'] for e in data['etapes']))
        self.assertTrue(all(k['marche'] for k in data['kinds']))
        self.assertEqual(len(data['etapes']), 8)


if __name__ == '__main__':
    unittest.main()
