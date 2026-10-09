#!/usr/bin/env python3
"""Interpréteur : un pipeline décrit uniquement en base tourne de bout en bout.

Scénario : un bouton ouvre un « sujet » ; une invocation sans LLM le rend
tel quel ; un lien lance « Chercheur », qui appelle la recherche web puis
propose deux fiches, dont une trop proche d'un business existant ; chaque
fiche écrite lance « Choisir », qui passe le business en POC_SELECTED. Le
modèle est simulé. Aucune ligne de code n'est propre à ces invocations.
"""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter import tools as tools_mod  # noqa: E402
from serge.interpreter.flow import fire_button, fire_due_triggers  # noqa: E402
from serge.interpreter.queue import (  # noqa: E402
    process_one,
    resume_interrupted,
)
from serge.interpreter.tasks import enqueue_task, start_task  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402

NOW = '2026-09-28T10:00:00+00:00'


def _v(source: str, value: str = '') -> dict[str, str]:
    return {'source': source, 'value': value}


PIPELINE: dict[str, Any] = {
    'schema_version': 1,
    'tools': [
        {
            'id': 'known_business_candidates',
            'title': 'Lire les business connus',
            'capability': 'db_read',
            'read': {
                'tables': ['ventures'],
                'columns': [
                    {'table': 'ventures', 'name': 'id'},
                    {'table': 'ventures', 'name': 'name', 'as': 'title'},
                    {'table': 'ventures', 'name': 'lifecycle', 'as': 'status'},
                ],
                'params': [
                    {'name': 'limit', 'type': 'integer', 'default': '200'}
                ],
            },
        }
    ],
    'writable_tables': [
        {
            'table': 'ventures',
            'insert': True,
            'update': True,
            'columns': [
                {'name': 'name'},
                {'name': 'description'},
                {'name': 'lifecycle'},
            ],
        },
        {
            'table': 'venture_sources',
            'insert': True,
            'columns': [
                {'name': 'venture_id'},
                {'name': 'doc_id'},
                {'name': 'cycle_id'},
            ],
        },
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
            'id': 'business_proches',
            'table': 'ventures',
            'method': 'shared_words',
            'threshold': 72,
            'columns': ['name', 'description'],
        }
    ],
    'invocations': [
        {
            'id': 'ouvrir',
            'type': 'capability',
            'capability': 'echo',
            'queue': 'works',
            'params': {'sujet': _v('task', 'sujet')},
            'output': [{'path': 'sujet', 'type': 'text'}],
        },
        {
            'id': 'chercheur',
            'title': 'Chercheur',
            'type': 'llm',
            'prompt': 'Propose des business.',
            'gets_serge_intro': True,
            'default_max_rows': 1,
            'tools': [
                {
                    'tool': 'known_business_candidates',
                    'mode': 'given',
                    'label': 'Business connus',
                },
                {'tool': 'web_search', 'mode': 'callable'},
            ],
            'output': [
                {'path': 'fiches', 'type': 'list'},
                {'path': 'fiches.title', 'type': 'text'},
                {'path': 'fiches.description', 'type': 'text'},
                {'path': 'fiches.pages', 'type': 'list', 'required': False},
            ],
            'writes': [
                {
                    'table': 'ventures',
                    'operation': 'insert',
                    'for_each': 'fiches',
                    'values': {
                        'name': _v('field', 'fiches.title'),
                        'description': _v('field', 'fiches.description'),
                        'lifecycle': _v('fixed', 'CANDIDATE'),
                    },
                },
                {
                    'table': 'venture_sources',
                    'operation': 'insert',
                    'for_each': 'fiches.pages',
                    'parent': 0,
                    'values': {
                        'venture_id': _v('parent_row', 'id'),
                        'doc_id': _v('field', 'fiches.pages'),
                        'cycle_id': _v('task', 'sujet'),
                    },
                },
            ],
        },
        {
            'id': 'choisir',
            'title': 'Choisir',
            'type': 'llm',
            'prompt': 'Choisis.',
            'output': [
                {'path': 'choix', 'type': 'list'},
                {'path': 'choix.venture_id', 'type': 'text'},
            ],
            'writes': [
                {
                    'table': 'ventures',
                    'operation': 'update',
                    'for_each': 'choix',
                    'key': {
                        'column': 'id',
                        'source': 'field',
                        'value': 'choix.venture_id',
                    },
                    'values': {'lifecycle': _v('fixed', 'POC_SELECTED')},
                }
            ],
        },
    ],
    'links': [
        {
            'id': 'ouvrir_chercheur',
            'from': 'ouvrir',
            'to': 'chercheur',
            'params': {'sujet': _v('task', 'sujet')},
        },
        {
            'id': 'chercheur_choisir',
            'from': 'chercheur',
            'to': 'choisir',
            'mode': 'per_row',
            'write': 0,
            'params': {'venture_id': _v('row', 'id')},
        },
    ],
    'triggers': [
        {
            'id': 'lancer',
            'invocation': 'ouvrir',
            'event': 'button',
            'params': {'sujet': _v('form', 'sujet')},
        }
    ],
}


class FakeModel:
    """Un faux modèle : répond selon l'invocation, et note ce qu'il reçoit."""

    def __init__(self, bad_first: bool = False, pick: str = '') -> None:
        self.calls: list[list[dict[str, Any]]] = []
        self.bad_first = bad_first
        self.pick = pick

    def __call__(self, _key, model, messages, **kwargs) -> ChatResult:
        self.calls.append(messages)
        system = messages[0]['content']
        if 'Propose des business' in system:
            if not any(m.get('role') == 'tool' for m in messages):
                call = ToolCall(
                    'c1', 'web_search', '{"query": "besoins artisans"}'
                )
                return ChatResult('', 10, 5, model, 3, (call,))
            if self.bad_first and len(self.calls) == 2:
                return ChatResult('pas du JSON', 10, 5, model, 3)
            answer = {
                'fiches': [
                    {
                        'title': 'Devis vocal pour artisans',
                        'description': 'dictez le devis au téléphone',
                        'pages': ['d1', 'd2'],
                    },
                    {
                        'title': 'Outil de relance',
                        'description': 'relancer les impayés des artisans',
                    },
                ]
            }
            return ChatResult(json.dumps(answer), 20, 30, model, 4)
        params = json.loads(messages[1]['content'].split('\n')[1])
        chosen = self.pick or params['venture_id']
        return ChatResult(
            json.dumps({'choix': [{'venture_id': chosen}]}), 5, 5, model, 2
        )


class InterpreterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        sans_pipeline_de_depart(self.conn)
        self.conn.execute(
            'INSERT INTO ventures(id, name, description, lifecycle,'
            " created_at, updated_at) VALUES('v_old', 'Relance des impayés',"
            " 'outil de relance des impayés des artisans', 'SMOKE_RUNNING',"
            " 't', 't')"
        )
        seed_pipeline(self.conn, PIPELINE)
        set_heartbeat(self.conn, True)  # Serge est arrêté par défaut
        self.conn.commit()
        fake_search = mock.patch.dict(
            tools_mod.RUNNERS,
            {
                'web_search': lambda *_a: {
                    'ok': True,
                    'rows': [{'title': 'page'}],
                }
            },
        )
        fake_search.start()
        self.addCleanup(fake_search.stop)

    def _run(self, model: FakeModel) -> str | None:
        return process_one(self.conn, 'works', now=NOW, caller=model)

    def _events(self, kind: str) -> list[dict]:
        return [
            json.loads(r[0])
            for r in self.conn.execute(
                'SELECT payload_json FROM events WHERE type=? ORDER BY id',
                (kind,),
            )
        ]

    def test_le_pipeline_tourne_de_bout_en_bout(self) -> None:
        model = FakeModel()
        self.assertIsNotNone(
            fire_button(self.conn, 'lancer', {'sujet': 'cy1'})
        )
        self._run(model)  # ouvrir
        self._run(model)  # chercheur
        rows = self.conn.execute(
            "SELECT id, name, lifecycle FROM ventures WHERE id<>'v_old'"
        ).fetchall()
        self.assertEqual(
            [(r[1], r[2]) for r in rows],
            [('Devis vocal pour artisans', 'CANDIDATE')],
        )
        new_id = rows[0][0]
        sources = self.conn.execute(
            'SELECT venture_id, doc_id, cycle_id FROM venture_sources ORDER BY doc_id'
        ).fetchall()
        self.assertEqual(
            sources, [(new_id, 'd1', 'cy1'), (new_id, 'd2', 'cy1')]
        )
        skipped = self._events('write.skipped')
        self.assertEqual(skipped[0]['similar_to'], 'v_old')
        system = model.calls[0][0]['content']
        self.assertIn('Qui est Serge', system)
        self.assertIn('fiches.title', system)
        self.assertIn('Business connus', model.calls[0][1]['content'])
        self.assertEqual(
            self.conn.execute(
                'SELECT rows_given, rows_left_out FROM task_inputs'
            ).fetchone(),
            (1, 0),
        )
        self._run(model)  # choisir
        self.assertEqual(
            self.conn.execute(
                'SELECT lifecycle FROM ventures WHERE id=?', (new_id,)
            ).fetchone(),
            ('POC_SELECTED',),
        )
        self.assertIsNone(self._run(model))
        usage = self.conn.execute(
            'SELECT point, verdict FROM llm_usage'
        ).fetchall()
        self.assertIn(('chercheur', 'ok'), usage)
        self.assertIn(('choisir', 'ok'), usage)

    def test_deux_cles_qui_commencent_pareil_font_deux_taches(self) -> None:
        """Deux appels de la même heure : leurs clés ne diffèrent qu'après
        le 20e caractère. La même clé rend toujours la même tâche."""
        premiere = enqueue_task(
            self.conn, 'chercheur', {}, key='appel:cdr_20261008T163512_a'
        )
        seconde = enqueue_task(
            self.conn, 'chercheur', {}, key='appel:cdr_20261008T164801_b'
        )
        self.assertIsNotNone(premiere)
        self.assertIsNotNone(seconde)
        self.assertNotEqual(premiere, seconde)
        self.assertEqual(
            enqueue_task(
                self.conn, 'chercheur', {}, key='appel:cdr_20261008T163512_a'
            ),
            premiere,
        )

    def test_un_business_deja_en_test_est_refuse(self) -> None:
        task = enqueue_task(self.conn, 'choisir', {'venture_id': 'v_old'})
        self.assertIsNotNone(task)
        self._run(FakeModel(pick='v_old'))
        self.assertEqual(
            self.conn.execute(
                "SELECT lifecycle FROM ventures WHERE id='v_old'"
            ).fetchone(),
            ('SMOKE_RUNNING',),
        )
        self.assertIn('non permis', self._events('write.refused')[0]['reason'])

    def test_une_reponse_mal_formee_est_redemandee(self) -> None:
        tache = enqueue_task(self.conn, 'chercheur', {'sujet': 'cy2'})
        self._run(FakeModel(bad_first=True))
        lignes = self.conn.execute(
            'SELECT verdict, task_id FROM llm_usage'
            " WHERE point='chercheur' ORDER BY id"
        ).fetchall()
        # Le tour d'outils (une recherche) est noté, puis les deux réponses.
        self.assertEqual(
            [r[0] for r in lignes], ['outil', 'format_invalide', 'ok']
        )
        # Chaque appel garde sa tâche : son coût va à son business.
        self.assertEqual({r[1] for r in lignes}, {tache})

    def test_une_tache_en_echec_n_ecrit_rien(self) -> None:
        self.conn.execute(
            "DELETE FROM writable_columns WHERE table_name='venture_sources'"
        )
        task = enqueue_task(self.conn, 'chercheur', {'sujet': 'cy3'})
        self.conn.commit()
        self._run(FakeModel())
        status, error = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (task,)
        ).fetchone()
        self.assertEqual(status, 'failed')
        self.assertIn('non inscriptible', error)
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM ventures WHERE id<>'v_old'"
            ).fetchone(),
            (0,),
        )
        self.assertEqual(len(self._events('task.failed')), 1)

    def test_un_lien_manuel_attend_un_clic(self) -> None:
        self.conn.execute(
            "UPDATE links SET auto=0 WHERE id='ouvrir_chercheur'"
        )
        fire_button(self.conn, 'lancer', {'sujet': 'cy4'})
        self._run(FakeModel())
        passage = self.conn.execute(
            "SELECT task_id FROM link_passages WHERE link_id='ouvrir_chercheur'"
        ).fetchone()
        self.assertEqual(passage, ('',))
        self.assertEqual(
            self.conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE invocation_id='chercheur'"
            ).fetchone(),
            (0,),
        )

    def test_une_invocation_eteinte_ne_recoit_pas_de_tache(self) -> None:
        self.conn.execute("UPDATE invocations SET enabled=0 WHERE id='ouvrir'")
        self.assertIsNone(
            fire_button(self.conn, 'lancer', {'sujet': 'x'}) or None
        )

    def test_un_declencheur_regulier_part_une_fois_par_intervalle(
        self,
    ) -> None:
        self.conn.execute(
            'INSERT INTO triggers(id, invocation_id, event, every_minutes)'
            " VALUES('toutes_5', 'ouvrir', 'every', 5)"
        )
        fire_due_triggers(self.conn, NOW)
        fire_due_triggers(self.conn, '2026-09-28T10:03:00+00:00')
        fire_due_triggers(self.conn, '2026-09-28T10:06:00+00:00')
        count = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE origin='trigger'"
        ).fetchone()
        self.assertEqual(count, (2,))

    def test_plafond_llm_du_jour_atteint(self) -> None:
        """Plafond atteint : la tâche LLM attend, la tâche sans LLM passe.

        Avec la policy de départ (5 € par jour, 0,9 € le dollar), le plafond
        est atteint à 5,56 $ de coût réel dans la journée. Un appel dont le
        coût n'est pas connu ne compte pas : il n'est pas estimé.
        """
        self.conn.execute(
            'INSERT INTO llm_usage(point, tier, model, tokens_in,'
            ' tokens_out, latency_ms, verdict, cost_usd, created_at)'
            " VALUES('x', 'mid', 'm', 1000000, 300000, 1, 'ok', 6.0, ?)",
            (NOW,),
        )
        llm = enqueue_task(self.conn, 'chercheur', {'sujet': 'cy5'})
        sans_llm = enqueue_task(self.conn, 'ouvrir', {'sujet': 'cy5'})
        self.conn.commit()
        model = FakeModel()
        self.assertEqual(self._run(model), sans_llm)
        self.assertIsNone(self._run(model))
        self.assertEqual(model.calls, [])
        self.assertEqual(
            self.conn.execute(
                'SELECT status FROM tasks WHERE id=?', (llm,)
            ).fetchone(),
            ('ready',),
        )

    def test_une_tache_interrompue_est_reprise(self) -> None:
        """Arrêt pendant une tâche : au redémarrage, elle repart de zéro."""
        task = enqueue_task(self.conn, 'ouvrir', {'sujet': 'cy6'})
        start_task(self.conn, str(task))
        self.conn.commit()
        self.assertIsNone(self._run(FakeModel()))
        self.assertEqual(resume_interrupted(self.conn, 'works'), [task])
        self.assertEqual(self._run(FakeModel()), task)
        self.assertEqual(
            self.conn.execute(
                'SELECT status, attempts FROM tasks WHERE id=?', (task,)
            ).fetchone(),
            ('done', 2),
        )
        self.assertEqual(len(self._events('task.resumed')), 1)

    def test_un_declencheur_a_heure_fixe_part_le_bon_jour(self) -> None:
        """« lun » à 08:30 (heure de Paris) : le lundi seulement, une fois."""
        self.conn.execute(
            'INSERT INTO triggers(id, invocation_id, event, at_time, at_days)'
            " VALUES('lundi', 'ouvrir', 'at', '08:30', 'lun')"
        )
        dimanche = '2026-09-27T07:00:00+00:00'  # 9 h à Paris, dimanche
        lundi_tot = '2026-09-28T06:00:00+00:00'  # 8 h à Paris
        lundi = '2026-09-28T06:45:00+00:00'  # 8 h 45 à Paris
        for moment in (dimanche, lundi_tot, lundi, lundi):
            fire_due_triggers(self.conn, moment)
        count = self.conn.execute(
            "SELECT COUNT(*) FROM tasks WHERE origin='trigger'"
        ).fetchone()
        self.assertEqual(count, (1,))


if __name__ == '__main__':
    unittest.main()
