#!/usr/bin/env python3
"""Goldens graphe + business (épine, LLM, lignée euro)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_graphe import project_business, project_graphe  # noqa: E402

NOW = '2026-09-11T12:00:00+00:00'


class ProjGrapheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, schedulable,'
            " created_at, updated_at) VALUES('v1','Atelier','SMOKE_RUNNING',"
            "1,?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            " n_target, created_at, updated_at) VALUES"
            "('c1','v1','named','email','RUNNING',10,?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, email, regime,'
            " funnel_state, created_at, updated_at) VALUES"
            "('p1','v1','Ada','a@x.io','OUTBOUND','INTENT',?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            " status, idempotency_key, created_at, updated_at) VALUES"
            "('t1','c1','p1','email','sent','k1',?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            " intent_id, status, created_at, updated_at) VALUES"
            "('x1','v1','invoice',80,'in-1','paid',?,?)",
            (NOW, NOW),
        )
        self.conn.commit()

    def test_epine_et_llm(self) -> None:
        data = project_graphe(self.conn, {}, NOW)
        ids = [n['id'] for n in data['epine']]
        self.assertEqual(
            ids,
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
        self.assertGreaterEqual(len(data['llm']), 10)
        self.assertTrue(any(f['id'] == 'intent-caisse' for f in data['flux']))
        ecoute = next(n for n in data['epine'] if n['id'] == 'ecoute')
        self.assertEqual(ecoute['cible'], {'type': 'ecoute', 'id': 'pages'})
        self.assertEqual(ecoute['titre'], 'Écoute')

    def test_business_venture_et_voix(self) -> None:
        data = project_business(self.conn, {}, NOW)
        self.assertEqual(data['venture']['id'], 'v1')
        self.assertGreaterEqual(data['paid_eur'], 80)
        self.assertIn('encaissé', data['voix'])
        self.assertIn('personnes touchées', data['recit'])
        self.assertTrue(any(n.get('titre') for n in project_graphe(self.conn, {}, NOW)['llm']))
        types = [item['type'] for item in data['lignage']]
        self.assertIn('facture', types)
        self.assertIn('venture', types)
