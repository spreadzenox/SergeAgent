#!/usr/bin/env python3
"""Pipeline de départ : la base se remplit sans jamais être écrasée."""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.capabilities import CAPABILITIES, ensure_capabilities  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.db.query_builder import execute_db_read  # noqa: E402
from serge.db.query_errors import DbReadError  # noqa: E402
from serge.pipeline_seed import PipelineSeedError, seed_pipeline  # noqa: E402


def _pipeline(prompt: str = 'Trouve des besoins.') -> dict:
    return {
        'schema_version': 1,
        'writable_tables': [
            {
                'table': 'ventures',
                'insert': True,
                'update': True,
                'columns': [{'name': 'name'}, {'name': 'lifecycle'}],
            }
        ],
        'status_transitions': [
            {
                'table': 'ventures',
                'column': 'lifecycle',
                'from': '',
                'to': 'CANDIDATE',
            },
            {
                'table': 'ventures',
                'column': 'lifecycle',
                'from': 'CANDIDATE',
                'to': 'POC_SELECTED',
            },
        ],
        'dedup_rules': [
            {
                'id': 'ventures_proches',
                'table': 'ventures',
                'method': 'shared_words',
                'threshold': 72,
                'columns': ['name', 'description'],
            }
        ],
        'invocations': [
            {
                'id': 'chercheur',
                'title': 'Chercheur d’idées',
                'role': 'Proposer des business.',
                'step': 'pre_prospection',
                'type': 'llm',
                'model_tier': 'mid',
                'prompt': prompt,
                'tools': [
                    {
                        'tool': 'web_search',
                        'mode': 'callable',
                        'params': {'limit': {'source': 'fixed', 'value': '5'}},
                    }
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
                            'name': {
                                'source': 'field',
                                'value': 'fiches.title',
                            },
                            'lifecycle': {
                                'source': 'fixed',
                                'value': 'CANDIDATE',
                            },
                        },
                    }
                ],
            },
            {
                'id': 'choisir',
                'title': 'Choisir',
                'type': 'llm',
                'prompt': 'Choisis.',
            },
        ],
        'links': [
            {
                'id': 'chercheur_vers_choisir',
                'from': 'chercheur',
                'to': 'choisir',
                'mode': 'per_row',
                'write': 0,
                'params': {'venture_id': {'source': 'row', 'value': 'id'}},
            }
        ],
        'triggers': [
            {
                'id': 'chaque_lundi',
                'invocation': 'chercheur',
                'event': 'at',
                'at_time': '08:30',
                'at_days': 'lun',
            }
        ],
    }


class PipelineSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)

    def _one(self, sql: str, params: tuple = ()) -> tuple:
        return self.conn.execute(sql, params).fetchone()

    def test_le_depart_remplit_files_modeles_et_presentation(self) -> None:
        queues = {r[0] for r in self.conn.execute('SELECT id FROM queues')}
        self.assertEqual(queues, {'conversations', 'works'})
        tiers = {
            r[0] for r in self.conn.execute('SELECT tier FROM llm_models')
        }
        self.assertEqual(tiers, {'fast', 'mid', 'smart'})
        body = self._one(
            "SELECT body FROM serge_texts WHERE id='presentation'"
        )
        self.assertIn('Serge', body[0])

    def test_une_invocation_arrive_en_entier(self) -> None:
        seed_pipeline(self.conn, _pipeline())
        row = self._one(
            'SELECT type, model_tier, prompt, origin FROM invocations'
            " WHERE id='chercheur'"
        )
        self.assertEqual(row, ('llm', 'mid', 'Trouve des besoins.', 'code'))
        param = self._one(
            'SELECT p.param_name, p.source, p.value FROM invocation_tool_params p'
            ' JOIN invocation_tools t ON t.id=p.invocation_tool_id'
            " WHERE t.invocation_id='chercheur'"
        )
        self.assertEqual(param, ('limit', 'fixed', '5'))
        value = self._one(
            'SELECT v.source, v.value FROM invocation_write_values v'
            ' JOIN invocation_writes w ON w.id=v.write_id'
            " WHERE w.invocation_id='chercheur' AND v.column_name='name'"
        )
        self.assertEqual(value, ('field', 'fiches.title'))
        link = self._one(
            'SELECT l.write_id, w.invocation_id FROM links l'
            ' JOIN invocation_writes w ON w.id=l.write_id'
            " WHERE l.id='chercheur_vers_choisir'"
        )
        self.assertEqual(link[1], 'chercheur')
        self.assertEqual(
            self._one("SELECT at_time FROM triggers WHERE id='chaque_lundi'"),
            ('08:30',),
        )
        self.assertEqual(
            self._one(
                "SELECT COUNT(*) FROM status_transitions WHERE table_name='ventures'"
            ),
            (2,),
        )

    def test_rien_n_est_ecrase(self) -> None:
        seed_pipeline(self.conn, _pipeline())
        self.conn.execute(
            "UPDATE invocations SET prompt='Réglé dans MC' WHERE id='chercheur'"
        )
        self.conn.execute(
            "DELETE FROM invocation_tools WHERE invocation_id='chercheur'"
        )
        seed_pipeline(self.conn, _pipeline(prompt='Nouveau prompt du code'))
        self.assertEqual(
            self._one("SELECT prompt FROM invocations WHERE id='chercheur'"),
            ('Réglé dans MC',),
        )
        self.assertEqual(
            self._one(
                "SELECT COUNT(*) FROM invocation_tools WHERE invocation_id='chercheur'"
            ),
            (0,),
        )

    def test_une_invocation_supprimee_ne_revient_pas(self) -> None:
        seed_pipeline(self.conn, _pipeline())
        self.conn.execute(
            "UPDATE invocations SET deleted_at='2026-09-27' WHERE id='choisir'"
        )
        seed_pipeline(self.conn, _pipeline())
        self.assertEqual(
            self._one("SELECT deleted_at FROM invocations WHERE id='choisir'"),
            ('2026-09-27',),
        )

    def test_un_objet_nouveau_est_ajoute(self) -> None:
        seed_pipeline(self.conn, _pipeline())
        data = _pipeline()
        data['invocations'].append({'id': 'nouvelle', 'type': 'llm'})
        seed_pipeline(self.conn, data)
        self.assertIsNotNone(
            self._one("SELECT 1 FROM invocations WHERE id='nouvelle'")
        )

    def test_un_lien_vers_une_invocation_inconnue_est_refuse(self) -> None:
        data = _pipeline()
        data['links'][0]['to'] = 'fantome'
        with self.assertRaises(PipelineSeedError):
            seed_pipeline(self.conn, data)

    def test_les_capacites_absentes_restent_marquees(self) -> None:
        self.conn.execute(
            "INSERT INTO capabilities(id, title) VALUES('ancienne', 'Retirée')"
        )
        ensure_capabilities(self.conn)
        self.assertEqual(
            self._one(
                "SELECT available FROM capabilities WHERE id='ancienne'"
            ),
            (0,),
        )
        presentes = {
            r[0]
            for r in self.conn.execute(
                'SELECT id FROM capabilities WHERE available=1'
            )
        }
        self.assertEqual(presentes, {cap.id for cap in CAPABILITIES})
        sha = self._one(
            "SELECT code_sha FROM capabilities WHERE id='web_search'"
        )
        self.assertEqual(len(sha[0]), 64)

    def test_les_outils_de_depart_ont_leur_capacite(self) -> None:
        outils = dict(
            self.conn.execute('SELECT id, capability_id FROM tools').fetchall()
        )
        self.assertEqual(outils['web_search'], 'web_search')
        self.assertEqual(outils['listen_cycle_documents'], 'db_read')
        self.assertEqual(
            self._one(
                "SELECT montre_partout FROM tools WHERE id='demande_capacite'"
            ),
            (1,),
        )

    def test_les_pages_d_un_cycle_viennent_avec_leur_texte(self) -> None:
        """La jointure du catalogue est toujours faite (bug des capsules)."""
        for ident, titre in (('d1', 'Devis trop longs'), ('d2', 'Autre')):
            self.conn.execute(
                'INSERT INTO listen_docs(id, source, title, excerpt,'
                " fetched_at) VALUES(?, 'rss', ?, 'extrait', 't')",
                (ident, titre),
            )
        self.conn.execute(
            "INSERT INTO listen_cycle_docs(cycle_id, doc_id) VALUES('c1','d1')"
        )
        self.conn.execute(
            "INSERT INTO listen_cycle_docs(cycle_id, doc_id) VALUES('c2','d2')"
        )
        rows = execute_db_read(
            self.conn, 'listen_cycle_documents', {'cycle_id': 'c1'}
        )['data']
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['title'], 'Devis trop longs')
        self.assertEqual(rows[0]['excerpt'], 'extrait')

    def test_un_outil_deja_en_base_n_est_pas_ecrase(self) -> None:
        self.conn.execute(
            "UPDATE tools SET titre='Réglé dans MC' WHERE id='web_search'"
        )
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'tools': [
                    {
                        'id': 'web_search',
                        'title': 'Autre titre',
                        'capability': 'web_search',
                    }
                ],
            },
        )
        self.assertEqual(
            self._one("SELECT titre FROM tools WHERE id='web_search'"),
            ('Réglé dans MC',),
        )

    def test_un_outil_mal_decrit_est_refuse(self) -> None:
        for tool, erreur in (
            ({'id': 'x1', 'capability': 'db_read'}, PipelineSeedError),
            (
                {'id': 'x2', 'capability': 'web_search', 'read': {}},
                PipelineSeedError,
            ),
            (
                {
                    'id': 'x3',
                    'capability': 'db_read',
                    'read': {
                        'tables': ['ventures'],
                        'filters': [
                            {
                                'id': 'f',
                                'table': 'ventures',
                                'column': 'lifecycle',
                                'fixed': 'CANDIDATE',
                                'param': 'statut',
                            }
                        ],
                    },
                },
                DbReadError,
            ),
        ):
            with self.assertRaises(erreur):
                seed_pipeline(
                    self.conn, {'schema_version': 1, 'tools': [tool]}
                )

    def test_un_horaire_invalide_est_refuse(self) -> None:
        for mauvais in (
            {'at_time': '8h30', 'at_days': 'lun'},
            {'at_time': '08:30', 'at_days': 'mon'},
        ):
            data = _pipeline()
            data['triggers'][0].update(mauvais)
            with self.assertRaises(PipelineSeedError):
                seed_pipeline(self.conn, data)


if __name__ == '__main__':
    unittest.main()
