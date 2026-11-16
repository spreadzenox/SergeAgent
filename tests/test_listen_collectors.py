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
    TooManyReads,
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


# Atom : le lien de la page parmi d'autres, et le texte dans ``content``.
ATOM = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>T</title>
<entry><title>Avis PEA</title>
<link rel="replies" href="https://f.test/a/reponses"/>
<link rel="alternate" href="https://f.test/a"/>
<content type="html">&lt;p&gt;Un avis ?&lt;/p&gt;</content>
<updated>2026-11-16T21:13:29+00:00</updated></entry>
</feed>"""


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

    def test_parse_atom(self) -> None:
        docs = parse_rss(ATOM.encode(), 'forum-test')
        self.assertEqual(
            [(d['url'], d['title'], d['excerpt']) for d in docs],
            [('https://f.test/a', 'Avis PEA', '<p>Un avis ?</p>')],
        )
        self.assertEqual(docs[0]['published'], '2026-11-16T21:13:29+00:00')

    def test_parse_invalide(self) -> None:
        with self.assertRaisesRegex(ListenError, '^PARSE'):
            parse_rss(b'pas du xml {{{', 'x')

    def setUp(self) -> None:
        # Pas de réseau en test : l'adresse est jugée publique.
        patcher = mock.patch('serge.listen.page.check_host')
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_fetch_ok(self) -> None:
        with mock.patch(
            'urllib.request.urlopen', return_value=_response(RSS.encode())
        ) as mocked:
            docs = fetch_rss(
                'https://f.test/rss', 'forum-test', timeout=20, max_items=50
            )
        self.assertEqual(len(docs), 1)
        request = mocked.call_args[0][0]
        self.assertIn('SergeListen', request.get_header('User-agent'))

    def test_fetch_erreurs(self) -> None:
        with self.assertRaisesRegex(ListenError, '^NETWORK'):
            fetch_rss('ftp://x.test/rss', 'x', timeout=20, max_items=50)
        error = urllib.error.HTTPError(
            'https://x',
            404,
            'NF',
            {},
            None,  # type: ignore[arg-type]
        )
        with mock.patch('urllib.request.urlopen', side_effect=error):
            with self.assertRaisesRegex(
                ListenError, r'^NETWORK: HTTP 404 NF \(https://x.test/rss\)$'
            ):
                fetch_rss('https://x.test/rss', 'x', timeout=20, max_items=50)
        with mock.patch(
            'urllib.request.urlopen',
            side_effect=urllib.error.URLError('dns'),
        ):
            with self.assertRaisesRegex(ListenError, '^NETWORK'):
                fetch_rss('https://x.test/rss', 'x', timeout=20, max_items=50)

    def test_trop_de_lectures_l_attente_demandee(self) -> None:
        """L'attente vient de l'extérieur : en secondes dans l'un des deux
        en-têtes, sinon une minute ; une heure au plus."""
        for entetes, attente in (
            ({'Retry-After': '30'}, 31),
            ({'x-ratelimit-reset': '41.0'}, 42),
            ({}, 60),
            ({'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT'}, 60),
            ({'Retry-After': '-5'}, 1),
            ({'x-ratelimit-reset': '1794862800'}, 3600),
            ({'Retry-After': '1e999'}, 60),
        ):
            error = urllib.error.HTTPError(
                'https://x',
                429,
                'Too Many Requests',
                entetes,  # type: ignore[arg-type]
                None,  # type: ignore[arg-type]
            )
            with mock.patch('urllib.request.urlopen', side_effect=error):
                with self.assertRaises(TooManyReads) as refus:
                    fetch_rss(
                        'https://x.test/rss', 'x', timeout=20, max_items=50
                    )
            self.assertEqual(refus.exception.wait_s, attente, entetes)


if __name__ == '__main__':
    unittest.main()
