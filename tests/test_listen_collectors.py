#!/usr/bin/env python3
"""Collecteurs écoute : parse RSS/Atom, dédup, erreurs typées."""

from __future__ import annotations

import sys
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serge.listen.collectors import (  # noqa: E402
    ListenError,
    fetch_rss,
    parse_rss,
)

RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>T</title>
<item><title>Prix trop cher ?</title><link>https://f.test/a</link>
<description>Les artisans trouvent ça cher.</description>
<pubDate>Mon, 08 Sep 2026 10:00:00 GMT</pubDate></item>
<item><title>Doublon</title><link>https://f.test/a</link>
<description>x</description></item>
<item><title>Sans lien</title><description>y</description></item>
</channel></rss>"""


def _response(raw: bytes):
    response = mock.MagicMock()
    response.read.return_value = raw
    context = mock.MagicMock()
    context.__enter__.return_value = response
    context.__exit__.return_value = False
    return context


class CollectorsTests(unittest.TestCase):
    def test_parse_dedup(self) -> None:
        docs = parse_rss(RSS.encode(), 'forum-test')
        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc['title'], 'Prix trop cher ?')
        self.assertEqual(doc['url'], 'https://f.test/a')
        self.assertTrue(doc['id'].startswith('ld_'))
        self.assertIn('artisans', doc['excerpt'])

    def test_parse_invalide(self) -> None:
        with self.assertRaisesRegex(ListenError, '^PARSE'):
            parse_rss(b'pas du xml {{{', 'x')

    def test_fetch_ok(self) -> None:
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(RSS.encode())
        ) as mocked:
            docs = fetch_rss('https://f.test/rss', 'forum-test')
        self.assertEqual(len(docs), 1)
        request = mocked.call_args[0][0]
        self.assertIn('SergeListen', request.get_header('User-agent'))

    def test_fetch_erreurs(self) -> None:
        with self.assertRaisesRegex(ListenError, '^NETWORK'):
            fetch_rss('ftp://x.test/rss', 'x')
        error = urllib.error.HTTPError(
            'https://x',
            404,
            'NF',
            {},
            None,  # type: ignore[arg-type]
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(ListenError, '^NETWORK'):
                fetch_rss('https://x.test/rss', 'x')
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('dns'),
        ):
            with self.assertRaisesRegex(ListenError, '^NETWORK'):
                fetch_rss('https://x.test/rss', 'x')


if __name__ == '__main__':
    unittest.main()
