#!/usr/bin/env python3
"""Les appels au modèle : réessayer, noter chaque appel, finir proprement.

Scénarios :
- le modèle rend une réponse vide (ce qui a fait échouer « Explorer le
  web » en production) : l'appel est réessayé, et la tâche finit ;
- trois réponses vides : la tâche échoue, mais chaque appel raté reste
  noté ; une erreur qui ne passera pas (clé refusée) n'est pas réessayée ;
- chaque tour d'outils est noté et compte dans la dépense du jour ;
- quand les tours d'outils sont épuisés, le modèle est prévenu en clair ;
- le modèle peut appeler plusieurs outils d'un coup, et attend jusqu'à
  3 minutes une réponse ;
- une réponse vide garde ce qu'OpenRouter en dit.
"""

from __future__ import annotations

import io
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
from serge.interpreter import prompt  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.llm.client import ChatResult, LlmError, ToolCall, chat  # noqa: E402
from serge.llm.runtime import daily_tokens  # noqa: E402
from serge.pipeline_seed import seed_pipeline  # noqa: E402
from tests.taches_fixtures import sans_pipeline_de_depart  # noqa: E402

NOW = '2026-09-29T10:00:00+00:00'

PIPELINE: dict[str, Any] = {
    'schema_version': 1,
    'tools': [{'id': 'repeter', 'title': 'Répéter', 'capability': 'echo'}],
    'invocations': [
        {
            'id': 'chercher',
            'title': 'Chercher',
            'type': 'llm',
            'prompt': 'Cherche.',
            'max_tool_turns': 2,
            'tools': [{'tool': 'repeter', 'mode': 'callable'}],
            'output': [{'path': 'resultat', 'type': 'text'}],
        }
    ],
}

REPONSE = ChatResult(json.dumps({'resultat': 'trouvé'}), 10, 5, 'faux', 1)


def _outil(n: int) -> ChatResult:
    appels = tuple(
        ToolCall(f'c{i}', 'repeter', json.dumps({'x': i})) for i in range(n)
    )
    return ChatResult('', 7, 3, 'faux', 1, appels)


class Script:
    """Joue une suite de réponses (ou d'erreurs) ; garde chaque appel."""

    def __init__(self, *suite: ChatResult | Exception) -> None:
        self.suite = list(suite)
        self.appels: list[dict[str, Any]] = []

    def __call__(self, _key, _model, messages, **kwargs) -> ChatResult:
        self.appels.append({'messages': list(messages), **kwargs})
        suivant = self.suite.pop(0)
        if isinstance(suivant, Exception):
            raise suivant
        return suivant


class AppelsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        sans_pipeline_de_depart(self.conn)
        seed_pipeline(self.conn, PIPELINE)
        set_heartbeat(self.conn, True)
        self.conn.commit()
        patcher = mock.patch.object(prompt, 'PAUSES_S', (0.0, 0.0))
        patcher.start()
        self.addCleanup(patcher.stop)

    def _tourner(self, script: Script) -> tuple[str, str]:
        task = enqueue_task(self.conn, 'chercher', {})
        process_one(self.conn, 'works', now=NOW, caller=script)
        row = self.conn.execute(
            'SELECT status, last_error FROM tasks WHERE id=?', (task,)
        ).fetchone()
        return str(row[0]), str(row[1])

    def _verdicts(self) -> list[str]:
        return [
            str(r[0])
            for r in self.conn.execute(
                "SELECT verdict FROM llm_usage WHERE point='chercher'"
                ' ORDER BY id'
            )
        ]

    def test_une_reponse_vide_est_reessayee(self) -> None:
        vide = LlmError('EMPTY: OpenRouter empty reply')
        statut, _ = self._tourner(Script(vide, REPONSE))
        self.assertEqual(statut, 'done')
        self.assertEqual(self._verdicts(), ['erreur', 'ok'])

    def test_trois_reponses_vides_font_echouer_la_tache(self) -> None:
        vide = LlmError('EMPTY: OpenRouter empty reply')
        statut, erreur = self._tourner(Script(vide, vide, vide))
        self.assertEqual(statut, 'failed')
        self.assertIn('EMPTY', erreur)
        # Les appels ratés restent notés, même si la tâche échoue.
        self.assertEqual(self._verdicts(), ['erreur', 'erreur', 'erreur'])

    def test_une_cle_refusee_n_est_pas_reessayee(self) -> None:
        statut, _ = self._tourner(Script(LlmError('AUTH: key rejected')))
        self.assertEqual(statut, 'failed')
        self.assertEqual(self._verdicts(), ['erreur'])

    def test_chaque_tour_d_outils_est_note_et_compte(self) -> None:
        statut, _ = self._tourner(Script(_outil(2), REPONSE))
        self.assertEqual(statut, 'done')
        self.assertEqual(self._verdicts(), ['outil', 'ok'])
        jour = str(
            self.conn.execute('SELECT created_at FROM llm_usage').fetchone()[0]
        )[:10]
        self.assertEqual(daily_tokens(self.conn, jour), (17, 8))

    def test_le_modele_est_prevenu_quand_les_outils_sont_epuises(self) -> None:
        script = Script(_outil(1), _outil(1), REPONSE)
        statut, _ = self._tourner(script)
        self.assertEqual(statut, 'done')
        dernier = script.appels[-1]
        self.assertEqual(dernier['tool_choice'], 'none')
        self.assertEqual(
            dernier['messages'][-1],
            {'role': 'user', 'content': prompt.FIN_DES_OUTILS},
        )
        self.assertNotIn(
            prompt.FIN_DES_OUTILS,
            json.dumps(script.appels[0]['messages'], ensure_ascii=False),
        )

    def test_plusieurs_outils_par_tour_et_trois_minutes_d_attente(
        self,
    ) -> None:
        script = Script(_outil(3), REPONSE)
        self._tourner(script)
        self.assertTrue(script.appels[0]['parallel_tool_calls'])
        self.assertEqual(script.appels[0]['timeout'], 180.0)
        reponses_outils = [
            m for m in script.appels[1]['messages'] if m['role'] == 'tool'
        ]
        self.assertEqual(len(reponses_outils), 3)


class ReponseVideTests(unittest.TestCase):
    def test_la_raison_d_openrouter_est_gardee(self) -> None:
        corps = {
            'model': 'deepseek/deepseek-v4-flash',
            'choices': [
                {
                    'finish_reason': 'length',
                    'message': {'content': '', 'reasoning': 'je réfléchis'},
                }
            ],
        }
        reponse = io.BytesIO(json.dumps(corps).encode())
        reponse.__enter__ = lambda *_: reponse  # type: ignore[method-assign]
        reponse.__exit__ = lambda *_: None  # type: ignore[method-assign]
        with (
            mock.patch('urllib.request.urlopen', return_value=reponse),
            self.assertRaises(LlmError) as erreur,
        ):
            chat('cle', 'deepseek/deepseek-v4-flash', [])
        message = str(erreur.exception)
        self.assertTrue(message.startswith('EMPTY'))
        self.assertIn('fin : length', message)
        self.assertIn('modèle : deepseek/deepseek-v4-flash', message)
        self.assertIn('réflexion rendue sans réponse', message)


if __name__ == '__main__':
    unittest.main()
