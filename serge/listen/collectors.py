#!/usr/bin/env python3
"""Collecteurs écoute J0 : RSS fetch + parse (stdlib), dédup par lien.

Respect ToS lecture (timeout, cap items, user-agent identifié). Autres
sources (API/forums) : même contrat [{id, source, title, url, excerpt,
published}]. Erreurs typées ListenError (NETWORK/PARSE).
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

USER_AGENT = 'SergeListen/1.0 (+https://serge.local/bot-info)'


class ListenError(ValueError):
    pass


def _doc_id(source: str, url: str) -> str:
    digest = hashlib.sha256(f'{source}\n{url}'.encode()).hexdigest()
    return f'ld_{digest[:16]}'


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ''
    return ' '.join(element.text.split())


def parse_rss(
    raw: bytes, source: str, max_items: int = 50
) -> list[dict[str, str]]:
    """Parse un flux RSS/Atom (items bornés, champs nettoyés).

    Args:
        raw: Octets du flux.
        source: Nom source (dédup + traçabilité).
        max_items: Cap items.

    Returns:
        Docs [{id, source, title, url, excerpt, published}].

    Raises:
        ListenError: Flux illisible (PARSE).
    """
    try:
        text = raw.decode('utf-8', errors='replace')
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ListenError(f'PARSE: flux illisible ({exc})') from exc
    items = root.findall('.//item') or root.findall(
        './/{http://www.w3.org/2005/Atom}entry'
    )
    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items[: max(1, max_items)]:
        title = _text(item.find('title')) or _text(
            item.find('{http://www.w3.org/2005/Atom}title')
        )
        link_el = item.find('link')
        url = ''
        if link_el is not None:
            url = (link_el.get('href') or _text(link_el)).strip()
        excerpt = _text(item.find('description')) or _text(
            item.find('{http://www.w3.org/2005/Atom}summary')
        )
        published = _text(item.find('pubDate')) or _text(
            item.find('{http://www.w3.org/2005/Atom}updated')
        )
        if not url or url in seen:
            continue
        seen.add(url)
        docs.append(
            {
                'id': _doc_id(source, url),
                'source': source,
                'title': title[:200],
                'url': url[:500],
                'excerpt': excerpt[:800],
                'published': published[:40],
            }
        )
    return docs


def fetch_rss(
    url: str, source: str, timeout: float = 20.0, max_items: int = 50
) -> list[dict[str, str]]:
    """Récupère + parse un flux (timeout, user-agent, cap).

    Args:
        url: URL du flux (http/https).
        source: Nom source.
        timeout: Timeout HTTP.
        max_items: Cap items.

    Returns:
        Docs normalisés (dédup par lien).

    Raises:
        ListenError: NETWORK (transport/HTTP), PARSE (contenu).
    """
    if not url.startswith(('http://', 'https://')):
        raise ListenError('NETWORK: URL http(s) requise')
    request = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT}, method='GET'
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        raise ListenError(f'NETWORK: HTTP {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ListenError(f'NETWORK: flux injoignable ({exc})') from exc
    return parse_rss(raw, source, max_items)
