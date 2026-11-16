#!/usr/bin/env python3
"""Appeler les modèles d'Anthropic directement (décision Q97).

Anthropic est un faux client, qui répond des messages écrits à l'avance ;
la file, l'interpréteur, la policy et la base sont réels.

Scénarios :
- le réglage à « oui » : une tâche dont le modèle est ``anthropic/…`` part
  chez Anthropic, avec la clé de l'instance ; ses outils, ses résultats,
  le cache et la réflexion coupée sont au format d'Anthropic ; le coût est
  calculé avec les prix du catalogue ;
- le réglage à « non » (au départ) : tout passe par OpenRouter ;
- plus de crédit chez Anthropic : la tâche attend, un ticket le dit ;
- la traduction de l'historique : captures, résultats d'outils, messages
  réunis (logique piégeuse, testée seule).
"""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import anthropic
import httpx2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.coupe_circuit import set_heartbeat  # noqa: E402
from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm import anthropic_direct  # noqa: E402
from serge.llm.client import chat as openrouter_chat  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from serge.policy_store import set_setting  # noqa: E402

MAINTENANT = '2026-11-16T15:00:00+00:00'
PRIX = {
    'prompt_usd': 2.0,
    'completion_usd': 10.0,
    'cache_read_usd': 0.1,
    'cache_write_usd': 2.5,
}


class _Final:
    def __init__(self, message: dict[str, Any]) -> None:
        self.message = message

    def __enter__(self) -> _Final:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def get_final_message(self) -> _Final:
        return self

    def to_dict(self) -> dict[str, Any]:
        return self.message


class FakeAnthropic:
    """Le client d'Anthropic : note chaque requête, rend la réponse
    suivante (ou lève l'erreur suivante)."""

    instances: list[FakeAnthropic] = []
    replies: list[Any] = []

    def __init__(self, *, api_key: str, timeout: float) -> None:
        self.api_key = api_key
        self.requests: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self
        FakeAnthropic.instances.append(self)

    def stream(self, **params: Any) -> _Final:
        self.requests.append(json.loads(json.dumps(params)))
        reply = FakeAnthropic.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Final(reply)


def _message(content: list[dict[str, Any]], **usage: int) -> dict[str, Any]:
    return {
        'model': 'claude-sonnet-5-5',
        'stop_reason': 'tool_use'
        if content[-1]['type'] == 'tool_use'
        else 'end_turn',
        'content': content,
        'usage': {
            'input_tokens': usage.get('fresh', 100),
            'cache_read_input_tokens': usage.get('read', 0),
            'cache_creation_input_tokens': usage.get('written', 0),
            'output_tokens': usage.get('out', 10),
        },
    }


class DirectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        seed_pipeline(
            self.conn,
            {
                'schema_version': 1,
                'invocations': [
                    {'id': 'redacteur', 'type': 'llm', 'prompt': 'Écris.'}
                ],
            },
        )
        self.conn.execute('UPDATE triggers SET enabled=0')
        self.conn.execute(
            "UPDATE llm_models SET model='anthropic/claude-sonnet-5.5'"
        )
        set_heartbeat(self.conn, True)
        self.conn.commit()
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.root = Path(dossier.name)
        (self.root / 'secrets').mkdir()
        (self.root / 'secrets/anthropic-api-key').write_text('cle-de-test\n')
        FakeAnthropic.instances, FakeAnthropic.replies = [], []
        for patch in (
            mock.patch.object(anthropic, 'Anthropic', FakeAnthropic),
            mock.patch.object(
                anthropic_direct, '_catalog_prices', lambda _m: dict(PRIX)
            ),
        ):
            patch.start()
            self.addCleanup(patch.stop)

    def _tache(self) -> str:
        task_id = str(enqueue_task(self.conn, 'redacteur', {'cle': 'a'}))
        self.conn.commit()
        return task_id

    def _direct(self, valeur: str) -> None:
        self.assertEqual(
            set_setting(self.conn, 'llm_calls.anthropic_direct', valeur, 't'),
            '',
        )
        self.conn.commit()

    def test_oui_la_tache_part_chez_anthropic(self) -> None:
        self._direct('oui')
        task_id = self._tache()
        outil = {
            'type': 'tool_use',
            'id': 'toolu_1',
            'name': 'lire_historique',
            'input': {'table': 'x'},
        }
        FakeAnthropic.replies = [
            _message(
                [{'type': 'thinking', 'thinking': 'je lis'}, outil],
                fresh=1000,
                written=0,
            ),
            _message(
                [{'type': 'text', 'text': '{"text": "fini"}'}],
                fresh=50,
                read=1000,
                written=200,
                out=20,
            ),
        ]
        process_one(
            self.conn, 'works', now=MAINTENANT, caller=None, root=self.root
        )
        statut = self.conn.execute(
            'SELECT status FROM tasks WHERE id=?', (task_id,)
        ).fetchone()[0]
        self.assertEqual(statut, 'done')
        self.assertEqual(
            {c.api_key for c in FakeAnthropic.instances}, {'cle-de-test'}
        )
        premier, second = [
            r for c in FakeAnthropic.instances for r in c.requests
        ]
        self.assertEqual(premier['model'], 'claude-sonnet-5-5')
        self.assertEqual(premier['thinking'], {'type': 'between_tools'})
        self.assertEqual(premier['fallbacks'], 'default')
        self.assertIn('Écris.', premier['system'])
        self.assertEqual(premier['messages'][0]['role'], 'user')
        self.assertNotIn('cache_control', premier, 'pas encore d’outil')
        self.assertTrue(
            all('input_schema' in outil for outil in premier['tools'])
        )
        # Le second appel renvoie l'appel d'outil et son résultat, sans la
        # réflexion, et demande le cache.
        self.assertEqual(second['cache_control'], {'type': 'ephemeral'})
        modele, resultat = second['messages'][1], second['messages'][2]
        self.assertEqual(modele['role'], 'assistant')
        self.assertEqual([b['type'] for b in modele['content']], ['tool_use'])
        self.assertEqual(resultat['content'][0]['type'], 'tool_result')
        self.assertEqual(resultat['content'][0]['tool_use_id'], 'toolu_1')
        usages = self.conn.execute(
            'SELECT tokens_in, cached_tokens, cache_write_tokens, cost_usd,'
            ' provider, model FROM llm_usage ORDER BY rowid'
        ).fetchall()
        dernier = usages[-1]
        self.assertEqual(dernier[:3], (1250, 1000, 200))
        # 50 × 2 + 1000 × 0,1 + 200 × 2,5 + 20 × 10, par million.
        self.assertAlmostEqual(dernier[3], 900 / 1_000_000)
        self.assertEqual(dernier[4], 'Anthropic (direct)')
        self.assertEqual(dernier[5], 'anthropic/claude-sonnet-5.5')

    def test_non_tout_passe_par_openrouter(self) -> None:
        appel, cle = anthropic_direct.caller_for(
            self.conn, 'anthropic/claude-sonnet-5.5', self.root
        )
        self.assertIs(appel, openrouter_chat)
        self._direct('oui')
        appel, _cle = anthropic_direct.caller_for(
            self.conn, 'deepseek/deepseek-v4', self.root
        )
        self.assertIs(appel, openrouter_chat, 'un modèle d’un autre')

    def test_sans_credit_la_tache_attend_et_le_dit(self) -> None:
        self._direct('oui')
        task_id = self._tache()
        requete = httpx2.Request('POST', 'https://api.anthropic.com/v1')
        FakeAnthropic.replies = [
            anthropic.BadRequestError(
                'Your credit balance is too low to access the Anthropic API.',
                response=httpx2.Response(400, request=requete),
                body=None,
            )
        ]
        process_one(
            self.conn, 'works', now=MAINTENANT, caller=None, root=self.root
        )
        statut = self.conn.execute(
            'SELECT status FROM tasks WHERE id=?', (task_id,)
        ).fetchone()[0]
        self.assertEqual(statut, 'ready')
        titres = [
            r[0]
            for r in self.conn.execute(
                "SELECT title FROM tickets WHERE type='FYI'"
            )
        ]
        self.assertEqual(titres, ['Anthropic n’a plus de crédit'])

    def test_sans_cle_l_appel_echoue_et_le_dit(self) -> None:
        with self.assertRaisesRegex(Exception, 'AUTH: pas de clé Anthropic'):
            anthropic_direct.chat('', 'anthropic/claude-haiku-5.5', [])


class TraductionTests(unittest.TestCase):
    def test_un_tour_d_outils_avec_une_capture(self) -> None:
        historique = [
            {'role': 'system', 'content': 'Tu es Serge.'},
            {'role': 'user', 'content': 'Paie.'},
            {
                'role': 'assistant',
                'content': None,
                'tool_calls': [
                    {
                        'id': 'a',
                        'type': 'function',
                        'function': {
                            'name': 'navigateur_agir',
                            'arguments': '{"action": "capture"}',
                        },
                    },
                    {
                        'id': 'b',
                        'type': 'function',
                        'function': {'name': 'x', 'arguments': '{coupé'},
                    },
                ],
            },
            {'role': 'tool', 'tool_call_id': 'a', 'content': '{"ok": true}'},
            {'role': 'tool', 'tool_call_id': 'b', 'content': '{"ok": false}'},
            {
                'role': 'user',
                'content': [
                    {'type': 'text', 'text': 'Voici la capture.'},
                    {
                        'type': 'image_url',
                        'image_url': {'url': 'data:image/png;base64,QUJD'},
                    },
                ],
            },
        ]
        system, messages = anthropic_direct.translate(historique)
        self.assertEqual(system, 'Tu es Serge.')
        self.assertEqual(
            [m['role'] for m in messages], ['user', 'assistant', 'user']
        )
        appels = messages[1]['content']
        self.assertEqual(appels[0]['input'], {'action': 'capture'})
        self.assertEqual(appels[1]['input'], {}, 'paramètres illisibles')
        dernier = messages[2]['content']
        self.assertEqual(
            [b['type'] for b in dernier],
            ['tool_result', 'tool_result', 'text', 'image'],
        )
        self.assertEqual(
            dernier[3]['source'],
            {'type': 'base64', 'media_type': 'image/png', 'data': 'QUJD'},
        )

    def test_le_nom_et_la_reflexion_de_chaque_modele(self) -> None:
        for modele, nom, reflexion in (
            (
                'anthropic/claude-sonnet-5.5',
                'claude-sonnet-5-5',
                {'type': 'between_tools'},
            ),
            (
                'anthropic/claude-haiku-5.5',
                'claude-haiku-5-5',
                {'type': 'disabled'},
            ),
            ('anthropic/claude-opus-5.5', 'claude-opus-5-5', None),
        ):
            requete = anthropic_direct._request(modele, '', [], None, None)
            self.assertEqual(requete['model'], nom)
            self.assertEqual(requete.get('thinking'), reflexion)
            self.assertEqual(
                'fallbacks' in requete, not nom.startswith('claude-haiku')
            )


if __name__ == '__main__':
    unittest.main()
