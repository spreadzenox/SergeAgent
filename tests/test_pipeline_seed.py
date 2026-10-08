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
from serge.pipeline_seed import (  # noqa: E402
    PipelineSeedError,
    ensure_pipeline,
    seed_pipeline,
)


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
        self.assertEqual(queues, {'conversations', 'voice', 'works'})
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
        # Celles du pipeline de départ ('' → CANDIDATE, CANDIDATE →
        # POC_SELECTED, '' → TEST pour le business d'essai), le fichier de
        # test n'en ajoute pas de nouvelle.
        self.assertEqual(
            self._one(
                "SELECT COUNT(*) FROM status_transitions WHERE table_name='ventures'"
            ),
            (3,),
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

    def test_une_instance_existante_recoit_ce_qui_lui_manque(self) -> None:
        """Le cas du serveur au kit d'essai : les business avaient déjà leurs
        changements de statut, sans « création → TEST » ; « Traiter une
        réponse » avait le prompt de la PR 1 du lot 8."""
        import yaml

        self.conn.execute(
            "DELETE FROM status_transitions WHERE to_value IN ('TEST',"
            " 'CONTACTING') AND from_value IN ('', 'NEW', 'QUALIFIED')"
        )
        ancien = yaml.safe_load(
            (ROOT / 'config/pipeline.yaml').read_text(encoding='utf-8')
        )
        ancien = next(
            c for c in ancien['changes'] if c['id'] == 'lot8_traiter_un_appel'
        )['set']['prompt']['from'].strip()
        self.conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='traiter_reponse'",
            (ancien,),
        )
        self.conn.execute(
            "DELETE FROM pipeline_changes WHERE id='lot8_traiter_un_appel'"
        )
        ensure_pipeline(self.conn)
        self.assertEqual(
            self._one(
                "SELECT COUNT(*) FROM status_transitions WHERE (to_value='TEST'"
                " AND from_value='') OR (to_value='CONTACTING' AND"
                " from_value IN ('NEW', 'QUALIFIED'))"
            ),
            (3,),
        )
        self.assertIn(
            'transcription d',
            self._one(
                "SELECT prompt FROM invocations WHERE id='traiter_reponse'"
            )[0],
        )

    def test_l_agent_vocal_deploye_recoit_ses_correctifs(self) -> None:
        """Le cas du serveur après le premier essai réel : l'agent vocal a
        l'ancien prompt, pas l'outil « Son e-mail », et l'ancien texte de
        début d'appel."""
        import yaml

        ancien = yaml.safe_load(
            (ROOT / 'config/pipeline.yaml').read_text(encoding='utf-8')
        )
        ancien = next(
            c for c in ancien['changes'] if c['id'] == 'voix_adresse_confirmee'
        )['set']['prompt']['from'].strip()
        self.conn.execute(
            "UPDATE invocations SET prompt=? WHERE id='parler_au_telephone'",
            (ancien,),
        )
        self.conn.execute(
            "DELETE FROM pipeline_changes WHERE id IN ('voix_adresse_confirmee',"
            " 'voix_email_du_contact')"
        )
        self.conn.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
            " (SELECT id FROM invocation_tools WHERE tool_id='email_du_contact')"
        )
        self.conn.execute(
            "DELETE FROM invocation_tools WHERE tool_id='email_du_contact'"
        )
        self.conn.execute(
            "DELETE FROM serge_texts WHERE id LIKE 'voice_opening_%'"
        )
        self.conn.execute(
            "INSERT INTO serge_texts(id, title, body) VALUES('voice_opening',"
            " 'Début d’un appel', 'dis bonjour')"
        )
        avant = self._one(
            'SELECT MAX(position) FROM invocation_tools'
            " WHERE invocation_id='parler_au_telephone'"
        )[0]
        ensure_pipeline(self.conn)
        self.assertIn(
            'ne se note qu',
            self._one(
                "SELECT prompt FROM invocations WHERE id='parler_au_telephone'"
            )[0],
        )
        self.assertEqual(
            self._one(
                'SELECT mode, label, position FROM invocation_tools'
                " WHERE tool_id='email_du_contact'"
            ),
            ('given', 'Son e-mail', avant + 1),
        )
        self.assertEqual(
            [
                row[0]
                for row in self.conn.execute(
                    "SELECT id FROM serge_texts WHERE id LIKE 'voice_opening%'"
                    ' ORDER BY id'
                ).fetchall()
            ],
            ['voice_opening_inbound', 'voice_opening_outbound'],
        )
        # L'ajout ne se fait qu'une fois : retiré ensuite, l'outil ne revient
        # pas au démarrage suivant.
        self.conn.execute(
            "DELETE FROM invocation_tools WHERE tool_id='email_du_contact'"
        )
        ensure_pipeline(self.conn)
        self.assertEqual(
            self._one(
                'SELECT COUNT(*) FROM invocation_tools'
                " WHERE tool_id='email_du_contact'"
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
        self.assertEqual(outils['pages_a_trier'], 'db_read')
        self.assertEqual(outils['lire_page_entiere'], 'page_read')
        self.assertEqual(outils['lire_flux_rss'], 'rss_read')
        self.assertEqual(
            self._one(
                "SELECT montre_partout FROM tools WHERE id='demande_capacite'"
            ),
            (1,),
        )

    def test_les_preuves_des_candidats_viennent_par_jointure(self) -> None:
        """La jointure du catalogue est toujours faite (bug des capsules)."""
        self.conn.executescript(
            'INSERT INTO ventures(id, name, lifecycle, created_at, updated_at)'
            " VALUES('v1', 'Devis', 'CANDIDATE', 't', 't'),"
            " ('v2', 'Autre', 'SMOKE_RUNNING', 't', 't');"
            'INSERT INTO listen_docs(id, source, title, excerpt, fetched_at)'
            " VALUES('d1', 'web', 'Devis trop longs', 'extrait', 't'),"
            " ('d2', 'web', 'Autre page', 'x', 't');"
            'INSERT INTO venture_sources(venture_id, doc_id, cycle_id)'
            " VALUES('v1', 'd1', 'c1'), ('v2', 'd2', 'c1');"
        )
        rows = execute_db_read(self.conn, 'preuves_des_candidats', {})['data']
        self.assertEqual(
            rows,
            [
                {
                    'venture_id': 'v1',
                    'title': 'Devis trop longs',
                    'apercu': 'extrait',
                }
            ],
        )

    def test_les_pages_a_trier_d_un_cycle(self) -> None:
        self.conn.executescript(
            'INSERT INTO listen_docs(id, source, title, cycle_id, label,'
            " fetched_at) VALUES('d1', 'rss', 'A trier', 'c1', '', 't'),"
            " ('d2', 'rss', 'Deja triee', 'c1', 'bruit', 't'),"
            " ('d3', 'rss', 'Autre cycle', 'c2', '', 't');"
        )
        rows = execute_db_read(self.conn, 'pages_a_trier', {'cycle_id': 'c1'})
        self.assertEqual([r['id'] for r in rows['data']], ['d1'])

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

    def test_les_reglages_et_les_quotas_de_depart(self) -> None:
        reglage = self._one(
            'SELECT value, min_value, max_value, policy FROM'
            " invocation_settings WHERE invocation_id='formuler_a'"
            " AND name='nombre_idees'"
        )
        self.assertEqual(reglage, ('3', '0', '10', 1))
        self.assertEqual(
            self._one(
                'SELECT counted_values, max_value FROM table_quotas'
                " WHERE id='places_de_test'"
            ),
            ('POC_SELECTED, SMOKE_READY, SMOKE_RUNNING, SMOKE_DONE', 3),
        )

    def test_ce_qui_est_retire_est_marque_supprime(self) -> None:
        """La démo du lot 6, encore en base sur une instance existante,
        avec une tâche restée en attente : elle est annulée."""
        self.conn.executescript(
            'INSERT INTO invocations(id, title, type) VALUES'
            " ('demo_formuler', 'Démo', 'llm');"
            'INSERT INTO tasks(id, invocation_id, queue_id,'
            ' idempotency_key, created_at)'
            " VALUES('t_demo', 'demo_formuler', 'works', 'k_demo', 't');"
            'INSERT INTO table_quotas(id, table_name, column_name,'
            " counted_values, max_value) VALUES('business_choisis',"
            " 'ventures', 'lifecycle', 'POC_SELECTED', 3);"
        )
        ensure_pipeline(self.conn)
        self.assertNotEqual(
            self._one(
                "SELECT deleted_at FROM invocations WHERE id='demo_formuler'"
            ),
            ('',),
        )
        self.assertIsNone(
            self.conn.execute(
                "SELECT 1 FROM table_quotas WHERE id='business_choisis'"
            ).fetchone()
        )
        self.assertEqual(
            self._one("SELECT status FROM tasks WHERE id='t_demo'"),
            ('cancelled',),
        )

    def test_les_droits_d_ecriture_ne_font_que_grandir(self) -> None:
        """Une instance du lot 6 reçoit les colonnes et opérations nouvelles."""
        self.conn.execute(
            "DELETE FROM writable_columns WHERE table_name='ventures'"
            " AND column_name='family'"
        )
        self.conn.execute(
            "UPDATE writable_tables SET can_delete=0 WHERE table_name='ventures'"
        )
        ensure_pipeline(self.conn)
        self.assertEqual(
            self._one(
                "SELECT can_delete FROM writable_tables WHERE table_name='ventures'"
            ),
            (1,),
        )
        self.assertIsNotNone(
            self.conn.execute(
                "SELECT 1 FROM writable_columns WHERE table_name='ventures'"
                " AND column_name='family'"
            ).fetchone()
        )

    def test_aucune_description_coupee_par_une_virgule(self) -> None:
        """Dans ``{…}``, une virgule non protégée coupe une description."""
        from serge.policy import config_dir, read_yaml_file

        data = read_yaml_file(config_dir() / 'pipeline.yaml')
        vides: list[str] = []

        def parcourir(obj: object, ou: str) -> None:
            if isinstance(obj, dict):
                for cle, valeur in obj.items():
                    if valeur is None:
                        vides.append(f'{ou}.{cle}')
                    parcourir(valeur, f'{ou}.{cle}')
            elif isinstance(obj, list):
                for n, valeur in enumerate(obj):
                    parcourir(valeur, f'{ou}[{n}]')

        parcourir(data, '')
        self.assertEqual(vides, [])

    def test_un_reglage_hors_bornes_est_refuse(self) -> None:
        from serge.interpreter.settings import SettingError

        data = _pipeline()
        data['invocations'][0]['settings'] = {
            'nombre': {'value': 12, 'min': 1, 'max': 10}
        }
        with self.assertRaises(SettingError):
            seed_pipeline(self.conn, data)


if __name__ == '__main__':
    unittest.main()
