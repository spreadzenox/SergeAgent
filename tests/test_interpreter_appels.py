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
- une réponse vide garde ce qu'OpenRouter en dit ;
- le coût réel donné par OpenRouter est noté, et c'est lui qui compte dans
  le plafond du jour (converti en euros) ; un appel sans coût connu est
  estimé à partir de ses jetons ;
- si le plafond est atteint en plein travail, le modèle doit répondre sans
  plus d'outil.
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
from serge.interpreter.intro import serge_text  # noqa: E402
from serge.interpreter.queue import process_one  # noqa: E402
from serge.interpreter.tasks import enqueue_task  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.llm.client import ChatResult, LlmError, ToolCall  # noqa: E402
from serge.llm.runtime import (  # noqa: E402
    budget_reached,
    daily_tokens,
    llm_spend,
)
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
        # Les pauses avant de réessayer (page Pipeline) ne font pas attendre
        # les tests.
        patcher = mock.patch('serge.interpreter.prompt.time.sleep')
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
            {
                'role': 'user',
                'content': serge_text(self.conn, 'tools_exhausted'),
            },
        )
        self.assertNotIn(
            serge_text(self.conn, 'tools_exhausted'),
            json.dumps(script.appels[0]['messages'], ensure_ascii=False),
        )

    def test_le_texte_change_sur_la_page_pipeline_est_envoye(self) -> None:
        self.conn.execute(
            "UPDATE serge_texts SET body='Réponds maintenant, sans outil.'"
            " WHERE id='tools_exhausted'"
        )
        script = Script(_outil(1), _outil(1), REPONSE)
        self._tourner(script)
        self.assertEqual(
            script.appels[-1]['messages'][-1]['content'],
            'Réponds maintenant, sans outil.',
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

    def test_le_cout_reel_est_note(self) -> None:
        reponse = ChatResult(REPONSE.text, 10, 5, 'faux', 1, (), 0.0021)
        self._tourner(Script(reponse))
        self.assertEqual(
            self.conn.execute('SELECT cost_usd FROM llm_usage').fetchall(),
            [(0.0021,)],
        )

    def test_le_plafond_atteint_arrete_les_outils(self) -> None:
        """Un tour d'outils à 10 $ (9 €) dépasse le plafond de 5 € : le
        tour suivant, le modèle doit répondre, sans outil."""
        cher = ChatResult('', 7, 3, 'faux', 1, _outil(1).tool_calls, 10.0)
        script = Script(cher, REPONSE)
        statut, _ = self._tourner(script)
        self.assertEqual(statut, 'done')
        self.assertEqual(script.appels[1]['tool_choice'], 'none')
        self.assertEqual(
            script.appels[1]['messages'][-1]['content'],
            serge_text(self.conn, 'tools_exhausted'),
        )

    def test_un_resultat_d_outil_geant_est_coupe(self) -> None:
        geant = ToolCall('c1', 'repeter', json.dumps({'x': 'a' * 50000}))
        script = Script(ChatResult('', 1, 1, 'faux', 1, (geant,)), REPONSE)
        self._tourner(script)
        reponse_outil = next(
            m for m in script.appels[1]['messages'] if m['role'] == 'tool'
        )
        self.assertLess(len(reponse_outil['content']), 20200)
        self.assertIn('résultat tronqué', reponse_outil['content'])

    def test_une_redemande_de_format_se_fait_sans_outil(self) -> None:
        mauvaise = ChatResult(json.dumps({'autre': 1}), 1, 1, 'faux', 1)
        script = Script(mauvaise, REPONSE)
        statut, _ = self._tourner(script)
        self.assertEqual(statut, 'done')
        redemande = script.appels[1]
        self.assertEqual(redemande['tool_choice'], 'none')
        self.assertIn(
            'ne respecte pas le format', redemande['messages'][-1]['content']
        )
        self.assertEqual(self._verdicts(), ['format_invalide', 'ok'])

    def test_les_resultats_de_recherche_ne_sont_pas_en_double(self) -> None:
        trouve = {'ok': True, 'query': 'q', 'results': [{'url': 'https://x'}]}
        with mock.patch('serge.listen.web.search_public', return_value=trouve):
            resultat = run_capability(
                self.conn,
                'web_search',
                'web_search',
                {'query': 'q'},
                'chercher',
            )
        self.assertNotIn('results', resultat)
        self.assertEqual(resultat['rows'], [{'url': 'https://x'}])


class DepenseTests(unittest.TestCase):
    """La dépense du jour : le coût réel, jamais une estimation."""

    def test_cout_reel_et_appels_sans_cout(self) -> None:
        conn = sqlite3.connect(':memory:')
        self.addCleanup(conn.close)
        init_schema(conn)
        conn.executemany(
            'INSERT INTO llm_usage(point, tier, tokens_in, tokens_out,'
            ' verdict, cost_usd, created_at) VALUES(?,?,?,?,?,?,?)',
            [
                ('a', 'mid', 1000, 0, 'ok', 0.5, '2026-09-29T10:00'),
                ('a', 'mid', 1500, 500, 'outil', None, '2026-09-29T10:01'),
                ('a', 'mid', 0, 0, 'erreur', None, '2026-09-29T10:02'),
                ('a', 'mid', 9999, 0, 'ok', 3.0, '2026-09-28T10:00'),
            ],
        )
        politique = {'budget': {'llm_daily_eur': 1.0, 'eur_per_usd': 0.9}}
        depense = llm_spend(conn, politique, '2026-09-29')
        # 0,5 $ × 0,9 = 0,45 € : le coût réel. Les 2 000 jetons d'un appel
        # dont le coût n'est pas connu ne sont pas estimés : ils sont
        # comptés à part.
        self.assertAlmostEqual(depense.eur, 0.45)
        self.assertEqual(depense.unknown_tokens, 2000)
        self.assertEqual(depense.tokens, 3000)
        self.assertEqual(budget_reached(conn, politique, '2026-09-29'), '')
        self.assertEqual(budget_reached(conn, politique, '2026-09-28'), 'jour')
        # Le plafond du mois compte tout septembre : 0,45 € + 2,70 €.
        politique['budget'].update(llm_daily_eur=5.0, monthly_eur=3.0)
        self.assertEqual(budget_reached(conn, politique, '2026-09-29'), 'mois')
        self.assertEqual(budget_reached(conn, politique, '2026-10-01'), '')


if __name__ == '__main__':
    unittest.main()
