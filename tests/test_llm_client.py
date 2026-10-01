#!/usr/bin/env python3
"""Client LLM : chat + usage, erreurs typées (mocké)."""

from __future__ import annotations

import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.llm.client import LlmError, chat  # noqa: E402


def _response(payload: dict):
    body = json.dumps(payload).encode('utf-8')
    response = mock.MagicMock()
    response.read.return_value = body
    context = mock.MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


class LlmClientTests(unittest.TestCase):
    def test_chat_retourne_texte_et_usage(self) -> None:
        payload = {
            'model': 'x-ai/grok-4',
            'choices': [{'message': {'content': '  Bonjour  '}}],
            'usage': {'prompt_tokens': 120, 'completion_tokens': 30},
        }
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(payload)
        ) as mocked:
            result = chat(
                'sk-key',
                'x-ai/grok-4',
                [{'role': 'user', 'content': 'hi'}],
                referer='https://x.test',
            )
        self.assertEqual(result.text, 'Bonjour')
        self.assertEqual((result.tokens_in, result.tokens_out), (120, 30))
        self.assertEqual(result.model, 'x-ai/grok-4')
        self.assertGreaterEqual(result.latency_ms, 0)
        request = mocked.call_args[0][0]
        self.assertIn('/chat/completions', request.full_url)
        self.assertTrue(
            request.get_header('Authorization').startswith('Bearer ')
        )
        self.assertNotIn('sk-key', request.full_url)
        self.assertEqual(result.tool_calls, ())

    def test_chat_accepte_tool_calls_sans_texte(self) -> None:
        payload = {
            'choices': [
                {
                    'message': {
                        'content': None,
                        'tool_calls': [
                            {
                                'id': 'c1',
                                'function': {
                                    'name': 'memory_search',
                                    'arguments': '{"query":"prix"}',
                                },
                            }
                        ],
                    }
                }
            ],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 4},
        }
        tools = [{'type': 'function', 'function': {'name': 'memory_search'}}]
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(payload)
        ) as mocked:
            result = chat(
                'k',
                'm',
                [{'role': 'user', 'content': 'hi'}],
                tools=tools,
                tool_choice='auto',
            )
        self.assertEqual(result.text, '')
        self.assertEqual(len(result.tool_calls), 1)
        self.assertEqual(result.tool_calls[0].name, 'memory_search')
        sent = json.loads(mocked.call_args[0][0].data.decode('utf-8'))
        self.assertEqual(sent['tools'], tools)
        self.assertEqual(sent['tool_choice'], 'auto')
        self.assertFalse(sent['parallel_tool_calls'])

    def test_usage_absent_vaut_zero(self) -> None:
        payload = {'choices': [{'message': {'content': 'ok'}}]}
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(payload)
        ):
            result = chat('k', 'm', [{'role': 'user', 'content': 'hi'}])
        self.assertEqual((result.tokens_in, result.tokens_out), (0, 0))
        self.assertEqual(result.model, 'm')

    def test_erreurs_typees(self) -> None:
        with self.assertRaisesRegex(LlmError, '^AUTH'):
            chat('', 'm', [])
        error = urllib.error.HTTPError(
            'https://x',
            401,
            'Unauthorized',
            {},
            None,  # type: ignore[arg-type]
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(LlmError, '^AUTH'):
                chat('k', 'm', [])
        error500 = urllib.error.HTTPError(
            'https://x',
            500,
            'Err',
            {},
            None,  # type: ignore[arg-type]
        )
        with mock.patch('urllib.request.urlopen', side_effect=error500):
            with self.assertRaisesRegex(LlmError, '^API'):
                chat('k', 'm', [])
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('dns'),
        ):
            with self.assertRaisesRegex(LlmError, '^NETWORK'):
                chat('k', 'm', [])
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'choices': []}),
        ):
            with self.assertRaisesRegex(LlmError, '^EMPTY'):
                chat('k', 'm', [])

    def test_secret_non_logue(self) -> None:
        import serge.llm.client as client_mod

        source = Path(client_mod.__file__ or '').read_text(encoding='utf-8')
        self.assertNotIn('print', source)
        self.assertNotIn('api_key)', source.replace('api_key: str', ''))


class CacheTests(unittest.TestCase):
    """Le cache des modèles d'Anthropic, demandé seulement dans une boucle."""

    OUTIL = {'role': 'tool', 'tool_call_id': 'c1', 'content': '{}'}
    OK = {
        'choices': [{'message': {'content': 'ok'}}],
        'usage': {'prompt_tokens': 1, 'completion_tokens': 1},
    }

    def _asks_for_cache(self, model: str, messages: list, **kwargs) -> bool:
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(self.OK)
        ) as mocked:
            chat(
                'sk-key',
                model,
                messages,
                tools=[{'type': 'function'}],
                **kwargs,
            )
        body = json.loads(mocked.call_args[0][0].data)
        if 'cache_control' in body:
            self.assertEqual(body['cache_control'], {'type': 'ephemeral'})
        return 'cache_control' in body

    def test_le_cache_est_demande_dans_une_boucle_d_outils_d_anthropic(
        self,
    ) -> None:
        start = [{'role': 'user', 'content': 'hi'}]
        loop = [*start, self.OUTIL]
        sonnet = 'anthropic/claude-sonnet-5.5'
        self.assertTrue(self._asks_for_cache(sonnet, loop))
        self.assertTrue(
            self._asks_for_cache('~anthropic/claude-sonnet-latest', loop)
        )
        # Pas au premier appel, ni sur la réponse finale forcée : un ou deux
        # appels coûteraient 25 % de plus au lieu d'économiser.
        self.assertFalse(self._asks_for_cache(sonnet, start))
        self.assertFalse(
            self._asks_for_cache(sonnet, loop, tool_choice='none')
        )
        # Les autres fournisseurs cachent seuls.
        for other in ('deepseek/deepseek-v4.1-flash', 'openai/gpt-6.1-sol'):
            self.assertFalse(self._asks_for_cache(other, loop), other)


if __name__ == '__main__':
    unittest.main()
