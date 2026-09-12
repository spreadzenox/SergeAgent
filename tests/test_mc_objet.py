#!/usr/bin/env python3
"""Fiches objet : projecteur + API owner."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.schema import init_schema  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from serge.scheduler import enqueue  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402

NOW = '2026-09-11T12:00:00+00:00'


class ProjObjetTests(unittest.TestCase):
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
            'INSERT INTO contacts(id, venture_id, display, email, regime,'
            " funnel_state, created_at, updated_at) VALUES"
            "('p1','v1','Ada','a@x.io','OUTBOUND','INTENT',?,?),"
            "('p2','v1','Chloé','c@x.io','INBOUND','CUSTOMER',?,?)",
            (NOW, NOW, NOW, NOW),
        )
        self.conn.commit()

    def test_prospect_vs_client(self) -> None:
        p = project_objet(self.conn, 'prospect', 'p1')
        self.assertIsNotNone(p)
        self.assertEqual(p['type'], 'prospect')
        c = project_objet(self.conn, 'client', 'p2')
        self.assertEqual(c['type'], 'client')
        self.assertIn('payé', c['pourquoi'])

    def test_llm_connu(self) -> None:
        fiche = project_objet(self.conn, 'llm', 'classify_reply')
        self.assertIsNotNone(fiche)
        self.assertEqual(fiche['type'], 'llm')
        self.assertTrue(fiche['champs'])
        titres = [c['titre'] for c in fiche['cadres']]
        self.assertIn('À quoi ça sert', titres)
        self.assertIn('D’où ça vient, où ça va', titres)
        self.assertIn('Le texte qu’on lui donne (prompt)', titres)
        self.assertIn('Ce qu’il a le droit de lire', titres)
        self.assertIn('Outils', titres)
        self.assertEqual(fiche['tableau']['titre'], 'Passages récents de ce jugement')

    def test_cluster_demand_clair(self) -> None:
        self.conn.execute(
            'INSERT INTO listen_docs(id, source, title, excerpt, fetched_at)'
            " VALUES('d1','rss','Freelances chrono','timer facturable',?)",
            (NOW,),
        )
        self.conn.commit()
        fiche = project_objet(self.conn, 'llm', 'cluster_demand')
        self.assertEqual(fiche['pourquoi'], '')
        blob = json.dumps(fiche, ensure_ascii=False)
        self.assertNotIn('ALERT/FYI', blob)
        self.assertNotIn('listen_docs', blob)
        self.assertNotIn('hypothèse smoke', blob.lower())
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertIn('Moyen', champs['Quel genre de modèle'])
        self.assertIn('deux temps', champs['Quelle sorte de jugement'])
        self.assertIn('tas de textes', champs['Si ça rate'])
        mat = next(c for c in fiche['cadres'] if 'droit de lire' in c['titre'])
        titres_m = [lien['titre'] for lien in mat['liens']]
        self.assertTrue(any('Grille' in t for t in titres_m))
        self.assertNotIn(
            'rubric_volume_intensite_recurrence_willingness', titres_m
        )
        flux = next(c for c in fiche['cadres'] if 'vient' in c['titre'])
        ids = [lien['id'] for lien in flux['liens']]
        self.assertIn('pages', ids)
        self.assertIn('grappe', ids)
        self.assertIn('page(s) en base', fiche['cadres'][0]['texte'])

    def test_pages_outils_notions(self) -> None:
        pages = project_objet(self.conn, 'ecoute', 'pages')
        self.assertEqual(pages['type'], 'ecoute')
        self.assertIn('vraiment lues', pages['titre'])
        outil = project_objet(self.conn, 'outil', 'memory_search')
        self.assertIn('mémoire', outil['pourquoi'])
        self.assertEqual(
            project_objet(self.conn, 'outil', 'couche5')['id'], 'memory_search'
        )
        fiche = project_objet(self.conn, 'llm', 'cluster_demand')
        ids_outils = [
            lien['id']
            for c in fiche['cadres']
            if c['titre'] == 'Outils'
            for lien in c['liens']
        ]
        self.assertEqual(ids_outils.count('memory_search'), 1)
        self.assertNotIn('couche5', ids_outils)
        nav = project_objet(self.conn, 'outil', 'navigateur')
        self.assertTrue(nav['cadres'][0].get('todo'))
        notion = project_objet(self.conn, 'notion', 'score_volume')
        self.assertIn('note', notion['pourquoi'])
        rub = project_objet(
            self.conn, 'contexte', 'rubric_volume_intensite_recurrence_willingness'
        )
        self.assertIn('Grille', rub['titre'])
        self.assertIn('volume', rub['pourquoi'])

    def test_sqlite_et_table(self) -> None:
        cat = project_objet(self.conn, 'sqlite', 'sqlite')
        self.assertEqual(cat['type'], 'sqlite')
        noms = [ligne['id'] for ligne in cat['tableau']['lignes']]
        self.assertIn('ventures', noms)
        self.assertIn('llm_usage', noms)
        table = project_objet(self.conn, 'table', 'ventures')
        self.assertEqual(table['type'], 'table')
        self.assertIn('id', str(table['tableau']['lignes']))
        self.assertGreater(int(table['champs'][2]['v']), 0)

    def test_llm_usage_et_contexte(self) -> None:
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            " tokens_out, latency_ms, verdict, created_at)"
            " VALUES('classify_reply','T1','nemo',10,4,40,'ok',?)",
            (NOW,),
        )
        self.conn.commit()
        rid = self.conn.execute('SELECT id FROM llm_usage').fetchone()[0]
        fiche = project_objet(self.conn, 'llm_usage', f'classify_reply:{rid}')
        self.assertEqual(fiche['type'], 'llm_usage')
        self.assertIn('Jetons lus', [c['k'] for c in fiche['champs']])
        mat = project_objet(self.conn, 'contexte', 'policy')
        self.assertEqual(mat['type'], 'contexte')
        self.assertIn('autorisent', mat['pourquoi'])

    def test_inconnu(self) -> None:
        self.assertIsNone(project_objet(self.conn, 'dragon', 'x'))
        self.assertIsNone(project_objet(self.conn, 'venture', 'nope'))

    def test_file_canon(self) -> None:
        enqueue(
            self.conn,
            kind='inbound.classify',
            idempotency_key='k-file',
            venture_id='v1',
        )
        fiche = project_objet(self.conn, 'file', 'canon')
        self.assertEqual(fiche['type'], 'file')
        self.assertEqual(fiche['id'], 'canon')
        self.assertTrue(fiche['tableau']['lignes'])
        self.assertNotIn('inbound.classify', str(fiche['tableau']))


    def test_etape_ecoute(self) -> None:
        fiche = project_objet(self.conn, 'etape', 'ecoute')
        self.assertEqual(fiche['type'], 'etape')
        self.assertIn('demande réelle', fiche['pourquoi'])
        titres = [c['titre'] for c in fiche['cadres']]
        self.assertIn('Jugements, dans l’ordre', titres)
        self.assertIn('Pourquoi ça dépend de avant', titres)
        liens = [
            lien['id']
            for cadre in fiche['cadres']
            for lien in cadre.get('liens') or []
        ]
        self.assertIn('cluster_demand', liens)
        self.assertIn('pages', liens)

    def test_etape_inconnue(self) -> None:
        self.assertIsNone(project_objet(self.conn, 'etape', 'dragon'))


class ApiObjetTests(McServerCase):
    def test_objet_auth_et_404(self) -> None:
        status, _, _ = self._request('GET', '/owner/api/objet?type=venture&id=v1')
        self.assertEqual(status, 401)
        cookie = self._auth_cookie()
        status, _, body = self._request(
            'GET',
            '/owner/api/objet?type=venture&id=absent',
            headers={'Cookie': cookie},
        )
        self.assertEqual(status, 404)
        data = json.loads(body.decode())
        self.assertEqual(data['code'], 'objet')

    def test_objet_file_vide(self) -> None:
        cookie = self._auth_cookie()
        status, _, body = self._request(
            'GET',
            '/owner/api/objet?type=file&id=canon',
            headers={'Cookie': cookie},
        )
        self.assertEqual(status, 200)
        data = json.loads(body.decode())
        self.assertEqual(data['type'], 'file')
        self.assertEqual(data['tableau']['lignes'], [])
