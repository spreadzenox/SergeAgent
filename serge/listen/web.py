#!/usr/bin/env python3
"""Recherche web publique en lecture seule pour les invocations d'écoute."""

from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen


class _ResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._in_title = False
        self._in_text = False

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        values = dict(attrs)
        classes = values.get('class') or ''
        if tag == 'a' and 'result__a' in classes:
            self._current = {'title': '', 'url': values.get('href') or ''}
            self._in_title = True
        elif self._current and 'result__snippet' in classes:
            self._in_text = True

    def handle_data(self, data: str) -> None:
        if self._current is None:
            return
        if self._in_title:
            self._current['title'] += data
        elif self._in_text:
            self._current['excerpt'] = self._current.get('excerpt', '') + data

    def handle_endtag(self, tag: str) -> None:
        if tag == 'a' and self._current and self._in_title:
            self._in_title = False
            self.items.append(self._current)
            self._current = None
        elif self._in_text and tag in {'a', 'div'}:
            self._in_text = False


def search_public(query: str, limit: int = 5) -> dict[str, object]:
    """Interroge DuckDuckGo HTML et retourne des résultats bornés."""
    query = query.strip()
    if not query:
        return {'ok': False, 'code': 'query_vide', 'results': []}
    request = Request(
        'https://html.duckduckgo.com/html/?q=' + quote(query),
        headers={'User-Agent': 'Serge/1.0 (public research)'},
    )
    try:
        with urlopen(request, timeout=8) as response:
            html = response.read(600_000).decode('utf-8', errors='replace')
    except Exception as exc:  # noqa: BLE001 — tool fail-soft
        return {
            'ok': False,
            'code': 'web_indisponible',
            'detail': str(exc),
            'results': [],
        }
    parser = _ResultsParser()
    parser.feed(html)
    results = []
    for item in parser.items[: max(1, min(limit, 10))]:
        results.append(
            {
                'title': item.get('title', '').strip(),
                'url': urljoin('https://duckduckgo.com', item.get('url', '')),
                'excerpt': item.get('excerpt', '').strip(),
            }
        )
    return {'ok': True, 'query': query, 'results': results}
