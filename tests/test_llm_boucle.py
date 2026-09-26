#!/usr/bin/env python3
"""Boucle d’outils : tours, refus, couple, voix sans mémoire."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.llm.boucle import executer_boucle  # noqa: E402
from serge.llm.client import ChatResult, ToolCall  # noqa: E402
from serge.llm.outils_exec import (  # noqa: E402
    CLE_QUOTAS,
    outils_pressables,
    peut_appeler,
    quota_couple,
    restants_par_outil,
    tours_max,
)
from serge.memory.search import index_document  # noqa: E402
from serge.policy import (  # noqa: E402
    PolicyError,
    fusionner_semence,
    load_policy,
    validate_policy,
)
from serge.registry import load_llm_points  # noqa: E402

POLICY = {
    'quotas': {
        'llm_outil_tours_max': 12,
        'memory_search_per_cycle_per_point': 3,
    }
}


def _spec(*, memory: bool, tools: list[str] | None = None, **extra):
    context: dict = dict(extra)
    declared: list[str] = []
    if memory:
        declared.append('memory_search')
    if tools is not None:
        declared.extend(tools)
    return {
        'verdict': 'LLM-1',
        'tier': 'T1',
        'enabled': True,
        'context': context,
        'db_tools': declared,
    }


class OutilsPressablesTests(unittest.TestCase):
    def test_declaration_offre_memory_search(self) -> None:
        self.assertEqual(
            outils_pressables(_spec(memory=True)), ('memory_search',)
        )

    def test_voix_sans_memoire_mais_identite(self) -> None:
        spec = _spec(
            memory=False,
            tools=['agenda', 'catalogue', 'fiches', 'identity_basique'],
        )
        self.assertEqual(outils_pressables(spec), ('identity_basique',))

    def test_memory_search_absent_reste_ferme(self) -> None:
        spec = _spec(memory=False, tools=['identity_basique'])
        self.assertEqual(outils_pressables(spec), ('identity_basique',))

    def test_demande_capacite_offerte_partout(self) -> None:
        conn = sqlite3.connect(':memory:')
        init_schema(conn)
        self.assertEqual(
            outils_pressables(_spec(memory=True), conn),
            ('memory_search', 'demande_capacite'),
        )
        conn.close()

    def test_prevu_sans_handler_ignore(self) -> None:
        self.assertEqual(
            outils_pressables(_spec(memory=False, tools=['agenda'])), ()
        )


class QuotaCoupleTests(unittest.TestCase):
    def test_tool_quotas_gagne(self) -> None:
        spec = _spec(memory=True, tool_quotas={'memory_search': 1})
        self.assertEqual(quota_couple(spec, 'memory_search', POLICY), 1)

    def test_tool_quota_memory_search(self) -> None:
        spec = {'context': {'tool_quotas': {'memory_search': 1}}}
        self.assertEqual(quota_couple(spec, 'memory_search', POLICY), 1)

    def test_defaut_policy_memory_search(self) -> None:
        self.assertEqual(
            quota_couple(_spec(memory=True), 'memory_search', POLICY), 3
        )

    def test_autre_outil_illimite(self) -> None:
        self.assertIsNone(
            quota_couple(_spec(memory=False), 'identity_basique', POLICY)
        )

    def test_demande_capacite_un_par_jugement(self) -> None:
        self.assertEqual(
            quota_couple(_spec(memory=False), 'demande_capacite', POLICY), 1
        )

    def test_restants_min_couple_et_tours(self) -> None:
        spec = _spec(memory=True, tool_quotas={'memory_search': 2})
        restants = restants_par_outil(
            ('memory_search', 'identity_basique'),
            spent={'memory_search': 1},
            spec=spec,
            policy=POLICY,
            tours_faits=3,
            tours_plafond=12,
        )
        self.assertEqual(restants['memory_search'], 1)
        self.assertEqual(restants['identity_basique'], 9)

    def test_tours_rabotes_a_12(self) -> None:
        self.assertEqual(
            tours_max({'quotas': {'llm_outil_tours_max': 99}}), 12
        )
        self.assertEqual(tours_max(POLICY), 12)


class PeutAppelerTests(unittest.TestCase):
    def test_inconnu_et_deja_fait_et_quota(self) -> None:
        spec = _spec(memory=True, tool_quotas={'memory_search': 1})
        pressables = ('memory_search',)
        self.assertEqual(
            peut_appeler(
                'navigateur',
                pressables=pressables,
                spent={},
                spec=spec,
                policy=POLICY,
                deja=set(),
                arguments='{}',
            ),
            'inconnu',
        )
        self.assertEqual(
            peut_appeler(
                'memory_search',
                pressables=pressables,
                spent={},
                spec=spec,
                policy=POLICY,
                deja={('memory_search', '{"query": "x"}')},
                arguments='{"query": "x"}',
            ),
            'deja_fait',
        )
        self.assertEqual(
            peut_appeler(
                'memory_search',
                pressables=pressables,
                spent={'memory_search': 1},
                spec=spec,
                policy=POLICY,
                deja=set(),
                arguments='{}',
            ),
            'quota_couple',
        )


def _call(text='', *, name='', args='{}', cid='c1', tokens=(1, 1)):
    calls = (ToolCall(cid, name, args),) if name else ()
    return ChatResult(text, tokens[0], tokens[1], 'm', 3, calls)


class BoucleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        init_schema(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    def test_sans_memoire_offre_demande_partout(self) -> None:
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            noms = [
                (item.get('function') or {}).get('name')
                for item in (kwargs.get('tools') or [])
            ]
            self.assertEqual(noms, ['demande_capacite'])
            self.assertTrue(
                any(
                    CLE_QUOTAS in str(item.get('content') or '')
                    for item in args[2]
                )
            )
            return _call('bonjour')

        result = executer_boucle(
            caller,
            'k',
            'm',
            [{'role': 'user', 'content': 'hi'}],
            spec=_spec(memory=False),
            policy=POLICY,
            conn=self.conn,
            point_name='p',
        )
        self.assertEqual((result.text, n['n']), ('bonjour', 1))

    def test_contexte_recoit_les_restants(self) -> None:
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            hist = args[2]
            blocs = [
                json.loads(item['content'])
                for item in hist
                if item.get('role') == 'system'
                and isinstance(item.get('content'), str)
                and CLE_QUOTAS in item['content']
            ]
            self.assertEqual(len(blocs), 1)
            if n['n'] == 1:
                self.assertEqual(blocs[0]['tours_restants'], 12)
                self.assertEqual(
                    blocs[0]['appels_restants']['memory_search'], 3
                )
                return _call(name='memory_search', args='{"query":"prix"}')
            self.assertEqual(blocs[0]['tours_restants'], 11)
            self.assertEqual(blocs[0]['appels_restants']['memory_search'], 2)
            return _call('ok')

        index_document(self.conn, 'lesson', 'l1', 'prix')
        self.conn.commit()
        result = executer_boucle(
            caller,
            'k',
            'm',
            [
                {'role': 'system', 'content': 'tu juges'},
                {'role': 'user', 'content': 'hi'},
            ],
            spec=_spec(memory=True),
            policy=POLICY,
            conn=self.conn,
            point_name='p',
        )
        self.assertEqual(result.text, 'ok')

    def test_aller_retour_puis_texte(self) -> None:
        index_document(self.conn, 'lesson', 'l1', 'objections prix artisans')
        self.conn.commit()
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            self.assertTrue(kwargs.get('tools'))
            if n['n'] == 1:
                return _call(name='memory_search', args='{"query":"prix"}')
            self.assertEqual(kwargs.get('tool_choice'), None)
            hist = args[2]
            self.assertEqual(hist[-1]['role'], 'tool')
            body = json.loads(hist[-1]['content'])
            self.assertTrue(body.get('results') or body.get('logged'))
            return _call('voilà')

        result = executer_boucle(
            caller,
            'k',
            'm',
            [{'role': 'user', 'content': 'hi'}],
            spec=_spec(memory=True),
            policy=POLICY,
            conn=self.conn,
            point_name='p',
        )
        self.assertEqual((result.text, n['n']), ('voilà', 2))
        self.assertEqual((result.tokens_in, result.tokens_out), (2, 2))

    def test_inconnu_renvoie_json_outil(self) -> None:
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            if n['n'] == 1:
                return _call(name='navigateur', args='{}')
            body = json.loads(args[2][-1]['content'])
            self.assertEqual(body, {'ok': False, 'code': 'inconnu'})
            return _call('ok')

        result = executer_boucle(
            caller,
            'k',
            'm',
            [],
            spec=_spec(memory=True),
            policy=POLICY,
            conn=self.conn,
            point_name='p',
        )
        self.assertEqual(result.text, 'ok')

    def test_plafond_tours_force_texte(self) -> None:
        policy = {'quotas': {'llm_outil_tours_max': 2}}
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            if kwargs.get('tool_choice') == 'none' or not kwargs.get('tools'):
                return _call('stop')
            return _call(name='identity_basique', args='{}', cid=f'c{n["n"]}')

        with mock.patch(
            'serge.llm.outils_exec.identite_serge',
            return_value={'email': 'a@b.c'},
        ):
            result = executer_boucle(
                caller,
                'k',
                'm',
                [],
                spec=_spec(memory=False, tools=['identity_basique']),
                policy=policy,
                conn=self.conn,
                point_name='p',
            )
        self.assertEqual(result.text, 'stop')
        self.assertEqual(n['n'], 3)

    def test_quota_epuise_retire_loutil(self) -> None:
        spec = _spec(
            memory=False,
            tools=['identity_basique'],
            tool_quotas={'identity_basique': 1},
        )
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            noms = [
                (item.get('function') or {}).get('name')
                for item in (kwargs.get('tools') or [])
            ]
            if n['n'] == 1:
                self.assertEqual(
                    noms, ['identity_basique', 'demande_capacite']
                )
                return _call(name='identity_basique', args='{"x":1}')
            self.assertEqual(noms, ['demande_capacite'])
            return _call('fin')

        with mock.patch(
            'serge.llm.outils_exec.identite_serge',
            return_value={'email': 'a@b.c'},
        ):
            result = executer_boucle(
                caller,
                'k',
                'm',
                [],
                spec=spec,
                policy=POLICY,
                conn=self.conn,
                point_name='p',
            )
        self.assertEqual((result.text, n['n']), ('fin', 2))

    def test_deja_fait_refuse(self) -> None:
        n = {'n': 0}

        def caller(*args, **kwargs):
            n['n'] += 1
            if n['n'] <= 2:
                return _call(
                    name='identity_basique', args='{}', cid=f'c{n["n"]}'
                )
            self.assertEqual(
                json.loads(args[2][-1]['content'])['code'], 'deja_fait'
            )
            return _call('fin')

        with mock.patch(
            'serge.llm.outils_exec.identite_serge',
            return_value={'email': 'a@b.c'},
        ):
            result = executer_boucle(
                caller,
                'k',
                'm',
                [],
                spec=_spec(memory=False, tools=['identity_basique']),
                policy=POLICY,
                conn=self.conn,
                point_name='p',
            )
        self.assertEqual(result.text, 'fin')


class PolicyEtRegistreTests(unittest.TestCase):
    def test_semence_a_12(self) -> None:
        self.assertEqual(load_policy()['quotas']['llm_outil_tours_max'], 12)

    def test_tours_au_dela_de_12_refuse(self) -> None:
        bad = load_policy()
        bad['quotas'] = dict(bad['quotas'])
        bad['quotas']['llm_outil_tours_max'] = 13
        with self.assertRaises(PolicyError):
            validate_policy(bad)

    def test_vieux_snapshot_recoit_le_plafond(self) -> None:
        old = load_policy()
        old['quotas'] = dict(old['quotas'])
        old['quotas'].pop('llm_outil_tours_max', None)
        fused = fusionner_semence(old)
        self.assertEqual(fused['quotas']['llm_outil_tours_max'], 12)

    def test_tool_quotas_inconnu_refuse(self) -> None:
        points = load_llm_points()
        name = next(iter(points))
        ctx = dict(points[name]['context'])
        ctx['tool_quotas'] = {'pas_un_outil': 1}
        points[name] = dict(points[name], context=ctx)
        from serge.registry import _valider_tool_quotas

        with self.assertRaises(PolicyError):
            _valider_tool_quotas(name, ctx)


if __name__ == '__main__':
    unittest.main()
