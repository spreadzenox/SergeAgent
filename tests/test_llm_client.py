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


if __name__ == '__main__':
    unittest.main()
