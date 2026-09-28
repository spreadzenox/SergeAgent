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

from serge.db.boot import init_schema  # noqa: E402
from serge.funnels.contacts import add_address  # noqa: E402
from serge.mc.proj_objet import project_objet  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.mc_server_case import McServerCase  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart, tache  # noqa: E402

NOW = '2026-09-11T12:00:00+00:00'


def _v(source: str, value: str = '') -> dict[str, str]:
    return {'source': source, 'value': value}


# Un bouton lance « Ouvrir » (sans LLM), qui passe la main à « Chercheur »
# (LLM), qui écrit des business.
PIPELINE = {
    'schema_version': 1,
    'writable_tables': [
        {
            'table': 'ventures',
            'insert': True,
            'columns': [{'name': 'name'}, {'name': 'lifecycle'}],
        }
    ],
    'invocations': [
        {
            'id': 'ouvrir',
            'title': 'Ouvrir',
            'role': 'Ouvre un cycle.',
            'type': 'capability',
            'capability': 'echo',
            'step': 'pre_prospection',
            'params': {'guide': _v('task', 'guide')},
        },
        {
            'id': 'chercheur',
            'title': 'Chercheur',
            'role': 'Propose des business.',
            'type': 'llm',
            'model_tier': 'smart',
            'step': 'pre_prospection',
            'prompt': 'Propose.',
            'tools': [
                {
                    'tool': 'business_candidats',
                    'mode': 'given',
                    'label': 'Business connus',
                    'max_rows': 20,
                },
                {'tool': 'web_search', 'mode': 'callable'},
            ],
            'output': [
                {'path': 'fiches', 'type': 'list'},
                {'path': 'fiches.title', 'type': 'text'},
            ],
            'writes': [
                {
                    'table': 'ventures',
                    'operation': 'insert',
                    'for_each': 'fiches',
                    'values': {
                        'name': _v('field', 'fiches.title'),
                        'lifecycle': _v('fixed', 'CANDIDATE'),
                    },
                }
            ],
        },
    ],
    'links': [{'id': 'l1', 'from': 'ouvrir', 'to': 'chercheur'}],
    'triggers': [
        {
            'id': 'lancer',
            'title': 'Lancer un cycle',
            'invocation': 'ouvrir',
            'event': 'button',
            'params': {'guide': _v('form', 'guide')},
        }
    ],
}


def _cadre(fiche: dict, titre: str) -> dict:
    return next(c for c in fiche['cadres'] if c['titre'] == titre)


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
            'INSERT INTO contacts(id, venture_id, display, regime, funnel_state, created_at, updated_at) VALUES(?,?,?,?,?,?,?),(?,?,?,?,?,?,?)',
            (
                'p1',
                'v1',
                'Ada',
                'OUTBOUND',
                'INTENT',
                NOW,
                NOW,
                'p2',
                'v1',
                'Chloé',
                'INBOUND',
                'CUSTOMER',
                NOW,
                NOW,
            ),
        )
        add_address(self.conn, 'p1', 'email', 'a@x.io')
        add_address(self.conn, 'p2', 'email', 'c@x.io')
        self.conn.execute(
            'INSERT INTO accounts_standing(id, venue, handle, cooldown_until,'
            ' updated_at, role, profile_path, secret_ref, login_url,'
            ' targets_json, login, password) VALUES'
            "('s1','reddit','u/serge','',?,"
            "'ecoute','/tmp/profil-reddit','reddit.session',"
            "'https://www.reddit.com/login',"
            '\'["https://www.reddit.com/r/freelance/"]\','
            "'u/serge','pw-demo')",
            (NOW,),
        )
        sans_pipeline_de_depart(self.conn)
        seed_pipeline(self.conn, PIPELINE)
        self.conn.commit()

    def test_prospect_vs_client(self) -> None:
        p = project_objet(self.conn, 'prospect', 'p1')
        self.assertIsNotNone(p)
        self.assertEqual(p['type'], 'prospect')
        c = project_objet(self.conn, 'client', 'p2')
        self.assertEqual(c['type'], 'client')
        self.assertIn('payé', c['pourquoi'])

    def test_fiche_invocation_llm(self) -> None:
        fiche = project_objet(self.conn, 'llm', 'chercheur')
        assert fiche is not None
        self.assertEqual(fiche['type'], 'llm')
        self.assertEqual(fiche['titre'], 'Chercheur')
        self.assertEqual(fiche['pourquoi'], 'Propose des business.')
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertTrue(champs['Niveau de modèle'].startswith('Intelligent'))
        self.assertEqual(
            _cadre(fiche, 'Le texte qu’on lui donne (prompt)')['texte'],
            'Propose.',
        )
        donnes = _cadre(
            fiche, 'Ce qu’elle lit d’office (ce qu’elle doit traiter)'
        )
        self.assertIn('20 lignes au plus', donnes['champs'][0]['v'])
        appelables = [
            lien['id']
            for lien in _cadre(fiche, 'Ce qu’elle peut appeler')['liens']
        ]
        self.assertEqual(
            appelables,
            [
                'web_search',
                'demande_capacite',
                'lire_historique',
                'lire_tables_vues',
            ],
        )
        self.assertEqual(
            _cadre(fiche, 'Le format de sa réponse')['champs'][1]['k'],
            'fiches.title',
        )
        ecriture = _cadre(fiche, 'Où sa réponse est écrite')['champs'][0]
        self.assertIn('Ajouter dans ventures', ecriture['k'])
        self.assertIn('name ← le champ « fiches.title »', ecriture['v'])
        self.assertIn('lifecycle ← « CANDIDATE »', ecriture['v'])
        lance_par = _cadre(fiche, 'Ce qui la lance')['liens']
        self.assertEqual([lien['id'] for lien in lance_par], ['l1'])
        self.assertEqual(
            fiche['tableau']['titre'], 'Passages récents de cette invocation'
        )

    def test_fiche_invocation_sans_llm(self) -> None:
        fiche = project_objet(self.conn, 'llm', 'ouvrir')
        assert fiche is not None
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(champs['Sorte'], 'sans modèle, capacité « echo »')
        self.assertIn('guide ←', champs['Paramètres de la capacité'])
        declencheur = _cadre(fiche, 'Ce qui la lance')['champs'][0]
        self.assertEqual(
            declencheur,
            {'k': 'Lancer un cycle', 'v': 'un bouton de Mission Control'},
        )
        suite = _cadre(fiche, 'Ce qu’elle lance ensuite')['liens']
        self.assertEqual(
            [(lien['type'], lien['id']) for lien in suite], [('lien', 'l1')]
        )
        self.assertIsNone(project_objet(self.conn, 'llm', 'inconnue'))

    def test_pages_vides_ne_feignent_pas(self) -> None:
        self.conn.execute('DELETE FROM listen_docs')
        pages = project_objet(self.conn, 'ecoute', 'pages')
        self.assertEqual(pages['tableau']['lignes'], [])
        self.assertIn('Aucune page en base', pages['cadres'][0]['todo'])

    def test_pages_et_outils(self) -> None:
        pages = project_objet(self.conn, 'ecoute', 'pages')
        self.assertEqual(pages['type'], 'ecoute')
        self.assertIn('vraiment lues', pages['titre'])
        outil = project_objet(self.conn, 'outil', 'memory_search')
        self.assertIn('leçons', outil['pourquoi'])
        self.assertEqual(
            project_objet(self.conn, 'outil', 'memory_search')['id'],
            'memory_search',
        )
        lecture = project_objet(self.conn, 'outil', 'business_candidats')
        assert lecture is not None
        champs = {
            c['k']: c['v']
            for c in _cadre(lecture, 'Ce qu’il a le droit de lire')['champs']
        }
        self.assertEqual(champs['Tables'], 'ventures')
        utilisateurs = _cadre(lecture, 'Invocations qui s’en servent')
        self.assertEqual(
            [lien['id'] for lien in utilisateurs['liens']], ['chercheur']
        )
        self.assertIsNone(project_objet(self.conn, 'outil', 'navigateur'))

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

    def test_llm_usage(self) -> None:
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            ' tokens_out, latency_ms, verdict, created_at)'
            " VALUES('chercheur','smart','nemo',10,4,40,'ok',?)",
            (NOW,),
        )
        self.conn.commit()
        rid = self.conn.execute('SELECT id FROM llm_usage').fetchone()[0]
        fiche = project_objet(self.conn, 'llm_usage', f'chercheur:{rid}')
        self.assertEqual(fiche['type'], 'llm_usage')
        self.assertEqual(fiche['titre'], f'Chercheur · passage {rid}')
        self.assertIn('Jetons lus', [c['k'] for c in fiche['champs']])

    def test_compte_web(self) -> None:
        fiche = project_objet(self.conn, 'compte', 's1')
        assert fiche is not None
        self.assertEqual(fiche['titre'], 'reddit · u/serge')
        vals = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(vals['Sert à'], 'Écouter')
        self.assertEqual(vals['Login'], 'u/serge')
        self.assertEqual(vals['Mot de passe'], 'pw-demo')
        self.assertEqual(vals['Nom du secret'], 'reddit.session')
        self.assertIn('freelance', vals['Cibles'])
        self.assertIn('en clair', fiche['pourquoi'])

    def test_inconnu(self) -> None:
        self.assertIsNone(project_objet(self.conn, 'dragon', 'x'))
        self.assertIsNone(project_objet(self.conn, 'venture', 'nope'))

    def test_file_canon_et_tache(self) -> None:
        task = tache(self.conn, 'ouvrir', {'guide': 'artisans'}, key='k-file')
        fiche = project_objet(self.conn, 'file', 'canon')
        self.assertEqual(fiche['type'], 'file')
        self.assertEqual(fiche['id'], 'canon')
        ligne = fiche['tableau']['lignes'][0]
        self.assertEqual(
            ligne['cellules'][1:4], ['Ouvrir', 'works', 'Prochaine']
        )
        fiche = project_objet(self.conn, 'task', task)
        assert fiche is not None
        self.assertEqual(fiche['titre'], 'Ouvrir')
        champs = {c['k']: c['v'] for c in fiche['champs']}
        self.assertEqual(champs['Paramètre guide'], 'artisans')

    def test_etape_ecoute(self) -> None:
        fiche = project_objet(self.conn, 'etape', 'pre_prospection')
        self.assertEqual(fiche['type'], 'etape')
        self.assertIn('demande réelle', fiche['pourquoi'])
        titres = [c['titre'] for c in fiche['cadres']]
        self.assertIn('Invocations, dans l’ordre des liens', titres)
        self.assertIn('Pourquoi ça dépend de avant', titres)
        ordre = _cadre(fiche, 'Invocations, dans l’ordre des liens')
        self.assertEqual(
            [lien['titre'] for lien in ordre['liens']],
            ['1. Ouvrir', '2. Chercheur'],
        )
        liens = [
            lien['id']
            for cadre in fiche['cadres']
            for lien in cadre.get('liens') or []
        ]
        self.assertIn('pages', liens)

    def test_etape_inconnue(self) -> None:
        self.assertIsNone(project_objet(self.conn, 'etape', 'dragon'))


class ApiObjetTests(McServerCase):
    def test_objet_auth_et_404(self) -> None:
        status, _, _ = self._request(
            'GET', '/owner/api/objet?type=venture&id=v1'
        )
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
