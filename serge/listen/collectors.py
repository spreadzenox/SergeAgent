#!/usr/bin/env python3
"""Collecteurs écoute J0 : RSS fetch + parse (stdlib), dédup par lien.

Respect ToS lecture (timeout, cap items, user-agent identifié). Autres
sources (API/forums) : même contrat [{id, source, title, url, excerpt,
published}]. Erreurs typées ListenError (NETWORK/PARSE).

Un site qui refuse une lecture trop rapprochée (HTTP 429) dit combien de
temps attendre : ``TooManyReads`` porte cette attente. Exemple : Reddit
accepte une lecture de flux par minute et répond ``x-ratelimit-reset: 41``
aux suivantes.
"""

from __future__ import annotations

import hashlib
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any

USER_AGENT = 'SergeListen/1.0 (+https://serge.local/bot-info)'
ATOM = '{http://www.w3.org/2005/Atom}'
# Après un refus « trop de lectures » : l'attente quand le site ne dit pas
# combien, et la plus longue qu'on accepte de lui (au-delà, le passage
# suivant de la veille relira le flux).
WAIT_S = 60
MAX_WAIT_S = 3600


class ListenError(ValueError):
    pass


class TooManyReads(ListenError):
    """Le site refuse une lecture trop rapprochée (HTTP 429).

    ``wait_s`` : les secondes à attendre avant de relire.
    """

    def __init__(self, message: str, wait_s: int) -> None:
        super().__init__(message)
        self.wait_s = wait_s


def _wait_s(headers: Any) -> int:
    """Les secondes à attendre après un refus « trop de lectures ».

    Le site le dit dans l'en-tête ``Retry-After`` ou, comme Reddit, dans
    ``x-ratelimit-reset`` ; sinon, une minute. Une seconde de marge (le
    site arrondit vers le bas), et jamais plus d'une heure : la valeur
    vient de l'extérieur.
    """
    for name in ('Retry-After', 'x-ratelimit-reset'):
        try:
            asked = int(float(str((headers or {}).get(name) or '')))
        except (ValueError, OverflowError):
            continue
        return min(max(asked, 0) + 1, MAX_WAIT_S)
    return WAIT_S


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
    items = root.findall('.//item') or root.findall(f'.//{ATOM}entry')
    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in items[: max(1, max_items)]:
        title = _text(item.find('title')) or _text(item.find(f'{ATOM}title'))
        link_el = item.find('link')
        if link_el is None:
            # Atom : le lien de la page est celui sans ``rel``, ou
            # « alternate » (les autres mènent au flux ou aux réponses).
            link_el = next(
                (
                    link
                    for link in item.findall(f'{ATOM}link')
                    if link.get('rel', 'alternate') == 'alternate'
                ),
                None,
            )
        url = ''
        if link_el is not None:
            url = (link_el.get('href') or _text(link_el)).strip()
        # Atom : le résumé, sinon le contenu (Reddit ne donne que lui).
        excerpt = (
            _text(item.find('description'))
            or _text(item.find(f'{ATOM}summary'))
            or _text(item.find(f'{ATOM}content'))
        )
        published = _text(item.find('pubDate')) or _text(
            item.find(f'{ATOM}updated')
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
    url: str, source: str, *, timeout: float, max_items: int
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
        TooManyReads: Le site demande d'attendre (HTTP 429).
    """
    from serge.listen.page import PageError, check_host

    if not url.startswith(('http://', 'https://')):
        raise ListenError('NETWORK: URL http(s) requise')
    try:
        check_host(url)
    except PageError as exc:
        raise ListenError(f'NETWORK: {exc}') from exc
    request = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT}, method='GET'
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(2_000_000)
    except urllib.error.HTTPError as exc:
        # La raison donnée en face, et le flux : c'est elle qu'on lit dans
        # Mission Control.
        reason = f'NETWORK: HTTP {exc.code} {str(exc.reason)[:100]} ({url})'
        if exc.code == 429:
            raise TooManyReads(reason, _wait_s(exc.headers)) from exc
        raise ListenError(reason) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ListenError(f'NETWORK: flux injoignable ({exc})') from exc
    return parse_rss(raw, source, max_items)
