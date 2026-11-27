#!/usr/bin/env python3
"""La recherche web par Anthropic (décision Q115).

Anthropic est un faux client, qui rend des messages écrits à l'avance ; la
base, la policy et le pipeline sont réels.

Scénarios :
- une recherche réussie : les adresses et les titres sont ceux de l'outil,
  l'extrait est la ligne du modèle ou, à défaut, le passage qu'il a cité ;
  la dépense (jetons et prix de la recherche) est notée pour l'invocation ;
- l'outil d'Anthropic rend une erreur, ou Anthropic refuse l'appel : la
  recherche échoue avec sa raison, jamais « aucun résultat » ;
- sans clé Anthropic : même chose, sans appel.
"""

from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import anthropic
import httpx2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.db.boot import init_schema  # noqa: E402
from serge.interpreter.tools import run_capability  # noqa: E402
from serge.listen import web  # noqa: E402

PRIX = {'prompt_usd': 0.1, 'completion_usd': 0.5}
DEVIS = 'https://forum.test/devis'
RELANCES = 'https://blog.test/relances/'


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


class FauxAnthropic:
    """Note chaque requête, rend la réponse suivante (ou lève l'erreur)."""

    def __init__(self, *reponses: Any) -> None:
        self.reponses = list(reponses)
        self.requetes: list[dict[str, Any]] = []
        self.beta = self
        self.messages = self

    def __call__(self, **_cle: object) -> FauxAnthropic:
        return self

    def stream(self, **params: Any) -> _Final:
        self.requetes.append(params)
        reponse = self.reponses.pop(0)
        if isinstance(reponse, Exception):
            raise reponse
        return _Final(reponse)


def _message(contenu: list[dict[str, Any]], fin: str = 'end_turn') -> dict:
    return {
        'model': 'claude-haiku-5-5',
        'stop_reason': fin,
        'content': contenu,
        'usage': {
            'input_tokens': 20000,
            'output_tokens': 400,
            'server_tool_use': {'web_search_requests': 1},
        },
    }


TROUVE = [
    {'type': 'server_tool_use', 'id': 's1', 'name': 'web_search', 'input': {}},
    {
        'type': 'web_search_tool_result',
        'tool_use_id': 's1',
        'content': [
            {
                'type': 'web_search_result',
                'url': DEVIS,
                'title': 'Quel outil pour mes devis ?',
                'encrypted_content': 'xxx',
                'page_age': '3 novembre 2026',
            },
            {
                'type': 'web_search_result',
                'url': RELANCES,
                'title': 'Relancer ses clients',
                'encrypted_content': 'yyy',
            },
        ],
    },
    {'type': 'text', 'text': f'{DEVIS} | Un artisan cherche un outil.\n'},
    {
        'type': 'text',
        'text': 'Et un article sur les relances.',
        'citations': [
            {
                'type': 'web_search_result_location',
                'url': RELANCES,
                'cited_text': 'Mes clients paient en retard.',
            }
        ],
    },
]


class RechercheTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(':memory:')
        self.conn.row_factory = sqlite3.Row
        self.addCleanup(self.conn.close)
        init_schema(self.conn)
        self.conn.commit()

    def _chercher(self, client: FauxAnthropic, cle: str = 'cle') -> dict:
        with (
            mock.patch.object(web.anthropic, 'Anthropic', client),
            mock.patch.object(web, 'read_secret_file', lambda _p: cle),
            mock.patch.object(web, '_catalog_prices', lambda _m: PRIX),
        ):
            return run_capability(
                self.conn,
                'web_search',
                'web_search',
                {'query': 'outil devis artisan'},
                'explorer_web',
            )

    def test_une_recherche_rend_les_resultats_de_l_outil(self) -> None:
        client = FauxAnthropic(_message(TROUVE))
        rendu = self._chercher(client)
        self.assertTrue(rendu['ok'], rendu)
        self.assertEqual(
            rendu['rows'],
            [
                {
                    'title': 'Quel outil pour mes devis ?',
                    'url': DEVIS,
                    'excerpt': 'Un artisan cherche un outil.',
                    'age': '3 novembre 2026',
                },
                {
                    'title': 'Relancer ses clients',
                    'url': RELANCES,
                    'excerpt': 'Mes clients paient en retard.',
                },
            ],
        )
        self.assertNotIn('usage', rendu)
        requete = client.requetes[0]
        self.assertEqual(requete['model'], 'claude-haiku-5-5')
        self.assertEqual(
            requete['tools'],
            [
                {
                    'type': 'web_search_20250305',
                    'name': 'web_search',
                    'max_uses': 1,
                    'user_location': {'type': 'approximate', 'country': 'FR'},
                }
            ],
        )
        self.assertEqual(
            requete['messages'],
            [{'role': 'user', 'content': 'outil devis artisan'}],
        )
        self.assertIn('adresse de la page | extrait', requete['system'])
        self.assertNotIn('{nombre}', requete['system'])
        # 20 000 jetons lus et 400 écrits, plus une recherche à 0,01 $.
        ligne = self.conn.execute(
            'SELECT point, tier, model, tokens_in, tokens_out, verdict,'
            ' cost_usd, provider FROM llm_usage'
        ).fetchone()
        self.assertEqual(
            tuple(ligne)[:6],
            (
                'explorer_web',
                'recherche',
                'anthropic/claude-haiku-5.5',
                20000,
                400,
                'ok',
            ),
        )
        self.assertAlmostEqual(ligne['cost_usd'], 0.0122)
        self.assertEqual(ligne['provider'], 'Anthropic (direct)')

    def test_une_erreur_de_l_outil_n_est_pas_zero_resultat(self) -> None:
        erreur = [
            TROUVE[0],
            {
                'type': 'web_search_tool_result',
                'tool_use_id': 's1',
                'content': {
                    'type': 'web_search_tool_result_error',
                    'error_code': 'too_many_requests',
                },
            },
        ]
        rendu = self._chercher(FauxAnthropic(_message(erreur)))
        self.assertFalse(rendu['ok'])
        self.assertEqual(rendu['code'], 'web_indisponible')
        self.assertIn('too_many_requests', rendu['detail'])
        self.assertEqual(rendu['rows'], [])

    def test_anthropic_refuse_l_appel(self) -> None:
        refus = anthropic.BadRequestError(
            'web search is not enabled',
            response=httpx2.Response(
                400,
                request=httpx2.Request('POST', 'https://api.anthropic.com'),
            ),
            body=None,
        )
        rendu = self._chercher(FauxAnthropic(refus))
        self.assertFalse(rendu['ok'])
        self.assertIn('web search is not enabled', rendu['detail'])
        self.assertEqual(
            self.conn.execute('SELECT COUNT(*) FROM llm_usage').fetchone()[0],
            0,
        )

    def test_sans_cle_la_recherche_le_dit(self) -> None:
        client = FauxAnthropic()
        with mock.patch.object(web.anthropic, 'Anthropic', client):
            rendu = web.search_public(
                'q', 5, {'search_max_results': 10}, api_key=''
            )
        self.assertFalse(rendu['ok'])
        self.assertIn('pas de clé Anthropic', str(rendu['detail']))
        self.assertEqual(client.requetes, [])


if __name__ == '__main__':
    unittest.main()
