#!/usr/bin/env python3
"""Lire une page web, à la bonne dose : un aperçu ou la page entière.

Une simple requête, sans navigateur. Le texte est découpé en lignes : une
ligne est un titre, un paragraphe ou un élément de liste. Exemple : un
aperçu de 5 lignes pour trier des pages, 300 lignes au plus pour les
invocations qui formulent des business. Le menu, les scripts et le pied
de page ne sont pas gardés.

Serge ne lit jamais une adresse de son propre serveur ou d'un réseau
privé : une page lue sur le web ne doit pas pouvoir le faire interroger
ses services internes, même par une redirection.
"""

from __future__ import annotations

import ipaddress
import socket
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urlsplit

USER_AGENT = 'Serge/1.0 (lecture publique)'
MAX_BYTES = 2_000_000
_BLOCKS = frozenset(
    {
        'p',
        'li',
        'h1',
        'h2',
        'h3',
        'h4',
        'h5',
        'h6',
        'blockquote',
        'pre',
        'dd',
        'dt',
        'td',
        'th',
        'figcaption',
    }
)
_SKIPPED = frozenset(
    {
        'script',
        'style',
        'noscript',
        'nav',
        'footer',
        'header',
        'aside',
        'form',
        'svg',
        'template',
        'button',
        'select',
    }
)


class PageError(ValueError):
    """La page ne peut pas être lue."""


class _Lines(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lines: list[str] = []
        self.title = ''
        self._skip = 0
        self._in_title = False
        self._current: list[str] = []

    def _flush(self) -> None:
        line = ' '.join(' '.join(self._current).split())
        if line:
            self.lines.append(line)
        self._current = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIPPED:
            self._skip += 1
        elif tag == 'title':
            self._in_title = True
        elif tag in _BLOCKS or tag == 'br':
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED:
            self._skip = max(0, self._skip - 1)
        elif tag == 'title':
            self._in_title = False
        elif tag in _BLOCKS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skip:
            self._current.append(data)

    def close(self) -> None:
        super().close()
        self._flush()


def text_lines(html: str) -> tuple[str, list[str]]:
    """Le titre et les lignes de texte d'une page HTML (ou d'un extrait)."""
    parser = _Lines()
    parser.feed(html)
    parser.close()
    return ' '.join(parser.title.split()), parser.lines


def check_host(url: str) -> None:
    """Refuse une adresse qui n'est pas publique (serveur, réseau privé)."""
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or not parts.hostname:
        raise PageError('adresse http(s) attendue')
    try:
        infos = socket.getaddrinfo(parts.hostname, None)
    except OSError as exc:
        raise PageError(f'site introuvable : {parts.hostname}') from exc
    for info in infos:
        if not ipaddress.ip_address(info[4][0]).is_global:
            raise PageError('adresse interne refusée')


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_host(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_html(url: str, timeout: float = 15.0) -> str:
    """Le HTML d'une page publique.

    Raises:
        PageError: Adresse refusée, site injoignable, ou pas une page HTML.
    """
    check_host(url)
    opener = urllib.request.build_opener(_SafeRedirect)
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with opener.open(request, timeout=timeout) as response:
            kind = response.headers.get_content_type()
            if kind not in (
                'text/html',
                'application/xhtml+xml',
                'text/plain',
            ):
                raise PageError(f'pas une page lisible ({kind})')
            charset = response.headers.get_content_charset() or 'utf-8'
            raw = response.read(MAX_BYTES)
    except urllib.error.HTTPError as exc:
        raise PageError(f'la page répond {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise PageError(f'page injoignable ({exc})') from exc
    return raw.decode(charset, errors='replace')


def read_page(url: str, max_lines: int) -> dict[str, object]:
    """Le titre et les premières lignes d'une page (toutes si 0).

    Returns:
        ``{ok, url, title, lines, total_lines}``, ou ``{ok: False, code,
        detail}`` si la page ne peut pas être lue.
    """
    try:
        title, lines = text_lines(fetch_html(url))
    except PageError as exc:
        return {'ok': False, 'code': 'page_illisible', 'detail': str(exc)}
    shown = lines[:max_lines] if max_lines > 0 else lines
    return {
        'ok': True,
        'url': url,
        'title': title,
        'lines': shown,
        'total_lines': len(lines),
    }
