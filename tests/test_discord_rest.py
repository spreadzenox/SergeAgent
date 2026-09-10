#!/usr/bin/env python3
"""Client REST Discord : routes, 429, erreurs typées (mocké)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.discord.rest import (  # noqa: E402
    DiscordError,
    bot_token,
    create_forum_post,
    delete_message,
    edit_message,
    get_channel,
    send_message,
    verify_token,
)


def _response(payload: dict, status: int = 200):
    body = json.dumps(payload).encode('utf-8')
    response = mock.MagicMock()
    response.read.return_value = body
    response.status = status
    context = mock.MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


def _http_error(code: int, body: str = '{}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        'https://discord.com/api/v10/x',
        code,
        'Err',
        {},
        io.BytesIO(body.encode()),  # type: ignore[arg-type]
    )


class DiscordRestTests(unittest.TestCase):
    def test_verify_et_channel(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': '999', 'username': 'serge'}),
        ) as mocked:
            me = verify_token('tok-fake-1')
        self.assertEqual(me['username'], 'serge')
        request = mocked.call_args[0][0]
        self.assertIn('/users/@me', request.full_url)
        self.assertTrue(request.get_header('Authorization').startswith('Bot '))
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': '1', 'name': 'urgent'}),
        ):
            channel = get_channel('tok-fake-2', '1')
        self.assertEqual(channel['name'], 'urgent')

    def test_user_agent_distinctif(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': '999'}),
        ) as mocked:
            verify_token('tok-fake-1')
        agent = mocked.call_args[0][0].get_header('User-agent')
        self.assertTrue(agent.startswith('DiscordBot ('))
        self.assertNotIn('Python-urllib', agent)

    def test_send_edit_delete(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 'm1'}),
        ) as mocked:
            sent = send_message('tok-fake-3', 'c1', {'content': 'hi'})
        self.assertEqual(sent['id'], 'm1')
        self.assertIn('/channels/c1/messages', mocked.call_args[0][0].full_url)
        self.assertEqual(mocked.call_args[0][0].get_method(), 'POST')
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 'm1'}),
        ) as mocked:
            edit_message('tok-fake-4', 'c1', 'm1', {'content': 'yo'})
        self.assertEqual(mocked.call_args[0][0].get_method(), 'PATCH')
        with mock.patch(
            'urllib.request.urlopen', return_value=_response({}, 204)
        ) as mocked:
            delete_message('tok-fake-5', 'c1', 'm1')
        self.assertEqual(mocked.call_args[0][0].get_method(), 'DELETE')

    def test_forum_post(self) -> None:
        with mock.patch(
            'urllib.request.urlopen',
            return_value=_response({'id': 'post1'}),
        ) as mocked:
            post = create_forum_post(
                'tok-fake-6',
                'forum1',
                'Titre du ticket',
                {'embeds': [{'title': 'x'}]},
            )
        self.assertEqual(post['id'], 'post1')
        request = mocked.call_args[0][0]
        self.assertIn('/channels/forum1/threads', request.full_url)
        body = json.loads(request.data.decode('utf-8'))
        self.assertEqual(body['name'], 'Titre du ticket')
        self.assertEqual(body['auto_archive_duration'], 10080)

    def test_429_puis_succes(self) -> None:
        with (
            mock.patch(
                'urllib.request.urlopen',
                side_effect=[
                    _http_error(429, '{"retry_after": 0.01}'),
                    _response({'id': 'm2'}),
                ],
            ),
            mock.patch('serge.discord.rest.time.sleep') as slept,
        ):
            sent = send_message('tok-fake-7', 'c1', {'content': 'hi'})
        self.assertEqual(sent['id'], 'm2')
        slept.assert_called_once()

    def test_erreurs_typees(self) -> None:
        with self.assertRaisesRegex(DiscordError, '^AUTH'):
            send_message('', 'c1', {'content': 'x'})
        with mock.patch(
            'urllib.request.urlopen', side_effect=_http_error(401)
        ):
            with self.assertRaisesRegex(DiscordError, '^AUTH'):
                verify_token('tok-fake-8')
        with mock.patch(
            'urllib.request.urlopen', side_effect=_http_error(403)
        ):
            with self.assertRaisesRegex(DiscordError, '^FORBIDDEN'):
                send_message('tok-fake-9', 'c1', {})
        with mock.patch(
            'urllib.request.urlopen', side_effect=_http_error(404)
        ):
            with self.assertRaisesRegex(DiscordError, '^NOT_FOUND'):
                get_channel('tok-fake-10', 'cZZ')
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('dns'),
        ):
            with self.assertRaisesRegex(DiscordError, '^NETWORK'):
                send_message('tok-fake-11', 'c1', {})

    def test_token_depuis_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / 'secrets').mkdir()
            (root / 'secrets/discord-bot-token').write_text(
                'tok-fichier-1\n', encoding='utf-8'
            )
            self.assertEqual(bot_token(root), 'tok-fichier-1')
            self.assertEqual(bot_token(root / 'vide'), '')


if __name__ == '__main__':
    unittest.main()
