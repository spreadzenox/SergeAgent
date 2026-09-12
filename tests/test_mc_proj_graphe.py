#!/usr/bin/env python3
"""Goldens graphe + business (épine, LLM, pensée cadrée)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.db.store import append_event  # noqa: E402
from serge.mc.proj_graphe import project_business, project_graphe  # noqa: E402
from serge.scheduler import claim, enqueue  # noqa: E402

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
        self.assertEqual(ecoute['objet'], {'type': 'etape', 'id': 'ecoute'})
        self.assertEqual(ecoute['titre'], 'Écoute')
        ids_j = [j['id'] for j in ecoute['jugements']]
        self.assertIn('cluster_demand', ids_j)
        self.assertTrue(ecoute['jugements'][0]['ordre'])

    def test_business_venture_et_voix(self) -> None:
        data = project_business(self.conn, {}, NOW)
        self.assertEqual(data['venture']['id'], 'v1')
        self.assertGreaterEqual(data['paid_eur'], 80)
        self.assertIn('encaissé', data['voix'])
        self.assertIn('personnes touchées', data['recit'])
        self.assertTrue(any(n.get('titre') for n in project_graphe(self.conn, {}, NOW)['llm']))
        self.assertNotIn('lignage', data)
        self.assertNotIn('timeline', project_graphe(self.conn, {}, NOW))

    def test_pensee_cadre(self) -> None:
        wid = enqueue(
            self.conn,
            kind='inbound.classify',
            idempotency_key='k-run',
            venture_id='v1',
        )
        claim(self.conn, wid)
        append_event(
            self.conn,
            actor='classify_reply',
            type='llm.io',
            venture_id='v1',
            payload={
                'point': 'classify_reply',
                'prompt': 'Classe ce message.',
                'sortie': 'Classe : positive.',
            },
        )
        io = project_graphe(self.conn, {}, NOW)['io']
        self.assertEqual(io['point'], 'classify_reply')
        self.assertEqual(io['jugement'], 'Classer une réponse')
        self.assertEqual(io['etape'], 'conversation')
        self.assertEqual(io['etape_titre'], 'Conversation')
        self.assertEqual(io['tache'], 'Classification d’une réponse')
        self.assertEqual(io['tache_id'], wid)
        self.assertEqual(io['venture'], 'Atelier')
        self.assertEqual(io['sortie'], 'Classe : positive.')
