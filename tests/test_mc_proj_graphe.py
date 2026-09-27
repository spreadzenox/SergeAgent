#!/usr/bin/env python3
"""Goldens graphe + business (étapes, invocations dans l'ordre des liens)."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_graphe import project_business, project_graphe  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.taches_fixtures import tache  # noqa: E402

NOW = '2026-09-11T12:00:00+00:00'


def _inv(ident: str, titre: str, etape: str) -> dict:
    return {
        'id': ident,
        'title': titre,
        'role': f'{titre}. Pour le test.',
        'type': 'capability',
        'capability': 'echo',
        'step': etape,
    }


# Un petit pipeline : un bouton lance « Ouvrir », qui passe la main à
# « Explorer », qui passe la main à « Concevoir » (étape suivante).
# « Isolée » n'a ni lien ni déclencheur.
PIPELINE = {
    'schema_version': 1,
    'invocations': [
        _inv('explorer', 'Explorer', 'pre_prospection'),
        _inv('isolee', 'Isolée', 'pre_prospection'),
        _inv('ouvrir', 'Ouvrir', 'pre_prospection'),
        _inv('concevoir', 'Concevoir', 'conception_poc'),
    ],
    'links': [
        {'id': 'l1', 'from': 'ouvrir', 'to': 'explorer'},
        {
            'id': 'l2',
            'title': 'Chaque business part en conception',
            'from': 'explorer',
            'to': 'concevoir',
        },
    ],
    'triggers': [{'id': 'b1', 'invocation': 'ouvrir', 'event': 'button'}],
}


class ProjGrapheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, name, lifecycle, schedulable,'
            " created_at, updated_at) VALUES('v1','Atelier','SMOKE_RUNNING',"
            '1,?,?)',
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO campaigns(id, venture_id, family, channel, state,'
            ' n_target, created_at, updated_at) VALUES'
            "('c1','v1','named','email','RUNNING',10,?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                'OUTBOUND',
                'INTENT',
                NOW,
                NOW,
            ),
        )
        add_address(self.conn, 'p1', 'email', 'a@x.io')
        self.conn.execute(
            'INSERT INTO touches(id, campaign_id, contact_id, channel,'
            ' status, idempotency_key, created_at, updated_at) VALUES'
            "('t1','c1','p1','email','sent','k1',?,?)",
            (NOW, NOW),
        )
        self.conn.execute(
            'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
            ' intent_id, status, created_at, updated_at) VALUES'
            "('x1','v1','invoice',80,'in-1','paid',?,?)",
            (NOW, NOW),
        )
        seed_pipeline(self.conn, PIPELINE)
        self.conn.commit()

    def test_epine_et_llm(self) -> None:
        data = project_graphe(self.conn, {}, NOW)
        ids = [n['id'] for n in data['epine']]
        self.assertEqual(
            ids,
            [
                'pre_prospection',
                'conception_poc',
                'prospection_light',
                'choix_venture',
                'build_venture',
                'prospection_lourde',
                'collect_feedback',
                'caisse',
            ],
        )
        self.assertEqual(
            [n['id'] for n in data['llm']],
            ['ouvrir', 'explorer', 'isolee', 'concevoir'],
        )
        self.assertEqual(
            data['flux'],
            [
                {
                    'id': 'l2',
                    'de': 'pre_prospection',
                    'vers': 'conception_poc',
                    'libelle': 'Chaque business part en conception',
                    'debit': 0,
                }
            ],
        )
        pre = next(n for n in data['epine'] if n['id'] == 'pre_prospection')
        self.assertEqual(
            pre['objet'], {'type': 'etape', 'id': 'pre_prospection'}
        )
        self.assertEqual(pre['titre'], 'Pré-prospection')
        self.assertEqual(
            [(j['id'], j['rang'], j['ordre']) for j in pre['jugements']],
            [('ouvrir', 1, True), ('explorer', 2, True), ('isolee', 0, False)],
        )
        self.assertEqual(pre['jugements'][0]['detail'], 'Ouvrir.')
        self.assertTrue(pre['marche'])

    def test_le_debit_compte_les_passages(self) -> None:
        self.conn.execute(
            'INSERT INTO link_passages(link_id, source_ref, created_at)'
            " VALUES('l2', 'task:t1', ?)",
            (NOW,),
        )
        flux = project_graphe(self.conn, {}, NOW)['flux']
        self.assertEqual(flux[0]['debit'], 1)

    def test_epine_refuse_un_id_hors_enum(self) -> None:
        self.conn.execute(
            'INSERT INTO pipeline_steps(id, enabled, rang)'
            " VALUES('extra',1,99)"
        )
        ids = [n['id'] for n in project_graphe(self.conn, {}, NOW)['epine']]
        self.assertNotIn('extra', ids)
        self.assertIn('pre_prospection', ids)

    def test_business_venture_et_voix(self) -> None:
        data = project_business(self.conn, {}, NOW)
        self.assertEqual(data['venture']['id'], 'v1')
        self.assertGreaterEqual(data['paid_eur'], 80)
        self.assertIn('encaissé', data['voix'])
        self.assertIn('personnes touchées', data['recit'])
        self.assertTrue(
            any(
                n.get('titre')
                for n in project_graphe(self.conn, {}, NOW)['llm']
            )
        )
        self.assertNotIn('lignage', data)
        self.assertNotIn('timeline', project_graphe(self.conn, {}, NOW))

    def test_pensee_cadre(self) -> None:
        self.assertIsNone(project_graphe(self.conn, {}, NOW)['io'])
        wid = tache(
            self.conn,
            'explorer',
            {'venture_id': 'v1'},
            key='k-run',
            status='running',
        )
        io = project_graphe(self.conn, {}, NOW)['io']
        self.assertEqual(io['point'], 'explorer')
        self.assertEqual(io['jugement'], 'Explorer')
        self.assertEqual(io['etape'], 'pre_prospection')
        self.assertEqual(io['etape_titre'], 'Pré-prospection')
        self.assertEqual(io['tache'], 'Explorer')
        self.assertEqual(io['tache_id'], wid)
        self.assertEqual(io['venture'], 'Atelier')
        self.assertEqual(io['sortie'], '')
        self.conn.execute(
            "UPDATE tasks SET status='done', finished_at=? WHERE id=?",
            (NOW, wid),
        )
        self.assertEqual(
            project_graphe(self.conn, {}, NOW)['io']['sortie'], 'done'
        )
