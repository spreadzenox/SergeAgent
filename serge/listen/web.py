#!/usr/bin/env python3
"""La recherche web des invocations : celle d'Anthropic (décision Q115).

Serge ne lit plus la page de résultats d'un moteur : DuckDuckGo la refuse
aux robots (une page « prouvez que vous êtes humain », prise à tort pour
une recherche sans résultat). Un petit appel à un modèle d'Anthropic, avec
l'outil de recherche web d'Anthropic, fait la recherche chez Anthropic.
Les adresses et les titres rendus sont ceux de l'outil, jamais récrits par
le modèle ; le modèle n'écrit que l'extrait de chaque résultat, sur une
ligne « adresse | extrait » (texte « Recherche web, consigne du modèle
qui cherche », page Pipeline).

Il faut la clé Anthropic de l'instance (``secrets/anthropic-api-key``),
que les modèles soient appelés chez Anthropic ou par OpenRouter. Sans
clé, ou si Anthropic refuse, la recherche rend une erreur avec sa raison :
jamais « aucun résultat ».

Une recherche coûte son prix fixe (réglage « Recherche web, prix d'une
recherche ») et les jetons du petit appel. Exemple : 20 000 jetons lus et
400 écrits avec Haiku 5.5, plus 0,01 $ de recherche, font 0,0122 $. La
dépense est notée comme un appel au modèle, au nom de l'invocation qui
cherche.
"""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Mapping
from typing import Any

import anthropic

from serge.db.store import utcnow
from serge.interpreter.intro import serge_text
from serge.llm.anthropic_direct import (
    Prices,
    _catalog_prices,
    _cost,
    _error,
    _thinking,
    anthropic_model,
)
from serge.paths import config_root
from serge.policy_store import policy_en_vigueur
from serge.secrets import read_secret_file

# L'outil de recherche d'Anthropic, appelé directement par le modèle (sans
# le tri des résultats par du code, que les versions suivantes ajoutent).
SEARCH_TOOL = 'web_search_20250305'
# De quoi écrire un extrait par résultat, pas davantage.
MAX_TOKENS = 4000
# Anthropic peut mettre un tour en pause : on le reprend au plus tant de fois.
RESUMES = 2
PROVIDER = 'Anthropic (direct)'
TIER = 'recherche'
_ADDRESS = re.compile(r'https?://[^\s|<>)\]]+')


def web_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """L'outil « Chercher sur le web » : cherche, note la dépense, et rend
    les résultats sous ``rows`` (ce que rend un outil repart au modèle à
    chaque tour, un doublon coûterait deux fois)."""
    pol = policy_en_vigueur(conn)
    limit = int(args.get('limit') or pol['tools']['search_results'])
    workspace = str(pol['llm_calls'].get('anthropic_workspace') or '').strip()
    cle = read_secret_file(config_root() / 'secrets/anthropic-api-key')
    result = dict(
        search_public(
            str(args.get('query') or ''),
            limit,
            pol['web'],
            api_key=cle,
            workspace_id=workspace,
            brief=serge_text(conn, 'recherche_web'),
        )
    )
    usage = result.pop('usage', None)
    if isinstance(usage, dict):
        _note_usage(conn, inv, usage)
    rows = result.pop('results', [])
    return {**result, 'rows': rows}


def search_public(
    query: str,
    limit: int,
    web: Mapping[str, Any],
    *,
    api_key: str = '',
    workspace_id: str = '',
    brief: str = '',
    client: Any = None,
    prices: Prices | None = None,
) -> dict[str, object]:
    """Fait une recherche chez Anthropic et rend au plus ``limit`` résultats.

    Args:
        query: La recherche.
        limit: Le nombre de résultats voulus.
        web: Les réglages « Lecture du web » (page Policy) : le modèle qui
            cherche, le pays, l'attente maximale, le nombre maximum de
            résultats et le prix d'une recherche.
        api_key: Clé Anthropic (jamais écrite au journal).
        workspace_id: Le workspace à utiliser, pour une clé qui vaut pour
            tous ceux du compte ; vide sinon.
        brief: La consigne du modèle qui cherche ; ``{nombre}`` y est
            remplacé par le nombre de résultats.
        client: Remplace le client Anthropic (tests).
        prices: Rend les prix d'un modèle (tests ; défaut : le catalogue).

    Returns:
        ``{ok, query, results: [{title, url, excerpt}], usage}``, ou
        ``{ok: False, code, detail, results: []}`` avec la raison.
    """
    query = query.strip()
    if not query:
        return {'ok': False, 'code': 'query_vide', 'results': []}
    if not api_key and client is None:
        return _failure(
            'pas de clé Anthropic (secrets/anthropic-api-key) : la recherche'
            ' web passe par Anthropic'
        )
    count = max(1, min(limit, int(web['search_max_results'])))
    model = str(web['search_model'])
    name = anthropic_model(model)
    tool: dict[str, Any] = {
        'type': SEARCH_TOOL,
        'name': 'web_search',
        'max_uses': 1,
    }
    if str(web.get('search_country') or '').strip():
        tool['user_location'] = {
            'type': 'approximate',
            'country': str(web['search_country']).strip().upper(),
        }
    params: dict[str, Any] = {
        'model': name,
        'max_tokens': MAX_TOKENS,
        'messages': [{'role': 'user', 'content': query}],
        'tools': [tool],
    }
    if brief:
        params['system'] = brief.replace('{nombre}', str(count))
    thinking = _thinking(name)
    if thinking:
        params['thinking'] = thinking
    if workspace_id:
        params['workspace_id'] = workspace_id
    client = client or anthropic.Anthropic(
        api_key=api_key, timeout=float(web['search_timeout_s'])
    )
    started = time.monotonic()
    blocks: list[dict[str, Any]] = []
    spent: dict[str, int] = {}
    stop = ''
    try:
        for _ in range(RESUMES + 1):
            with client.beta.messages.stream(**params) as stream:
                message: dict[str, Any] = stream.get_final_message().to_dict()
            blocks += [
                b for b in message.get('content') or [] if isinstance(b, dict)
            ]
            _add(spent, message.get('usage') or {})
            stop = str(message.get('stop_reason') or '')
            if stop != 'pause_turn':
                break
            params['messages'] = [
                params['messages'][0],
                {'role': 'assistant', 'content': blocks},
            ]
    except anthropic.APIConnectionError as exc:
        return _failure(f'Anthropic injoignable ({exc})')
    except anthropic.APIStatusError as exc:
        return _failure(str(_error(exc)))
    usage = _usage(
        spent,
        model,
        int((time.monotonic() - started) * 1000),
        float(web['search_cost_usd']),
        prices or _catalog_prices,
    )
    if stop == 'refusal':
        return _failure('Anthropic a refusé la recherche', usage)
    found, reason = _found(blocks)
    if reason:
        return _failure(reason, usage)
    excerpts = _excerpts(blocks)
    results = []
    for item in found[:count]:
        url = str(item.get('url') or '')
        row = {
            'title': str(item.get('title') or '').strip(),
            'url': url,
            'excerpt': excerpts.get(_key(url), ''),
        }
        if item.get('page_age'):
            row['age'] = str(item['page_age'])
        results.append(row)
    return {'ok': True, 'query': query, 'results': results, 'usage': usage}


def _failure(
    detail: str, usage: dict[str, Any] | None = None
) -> dict[str, object]:
    out: dict[str, object] = {
        'ok': False,
        'code': 'web_indisponible',
        'detail': detail,
        'results': [],
    }
    if usage:
        out['usage'] = usage
    return out


def _found(blocks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str]:
    """Les résultats de l'outil, sans doublon, et la raison d'un échec.

    Une erreur de l'outil arrive dans une réponse réussie : son contenu
    est alors un objet ``{error_code}`` au lieu d'une liste de résultats.
    """
    found: dict[str, dict[str, Any]] = {}
    searched = False
    for block in blocks:
        if block.get('type') == 'server_tool_use':
            searched = True
        if block.get('type') != 'web_search_tool_result':
            continue
        inner = block.get('content')
        if isinstance(inner, dict):
            code = inner.get('error_code') or '?'
            return [], f'la recherche d’Anthropic a échoué ({code})'
        for item in inner or []:
            if isinstance(item, dict) and item.get('url'):
                found.setdefault(_key(str(item['url'])), item)
    if not searched:
        return [], 'le modèle n’a pas lancé la recherche'
    return list(found.values()), ''


def _excerpts(blocks: list[dict[str, Any]]) -> dict[str, str]:
    """L'extrait de chaque adresse : la ligne « adresse | extrait » du
    modèle, sinon le passage de la page qu'il a cité (150 caractères au
    plus, donnés par Anthropic)."""
    cited: dict[str, str] = {}
    text = ''
    for block in blocks:
        if block.get('type') != 'text':
            continue
        text += str(block.get('text') or '')
        for quote in block.get('citations') or []:
            if isinstance(quote, dict) and quote.get('url'):
                cited.setdefault(
                    _key(str(quote['url'])),
                    str(quote.get('cited_text') or '').strip(),
                )
    written = {}
    for line in text.splitlines():
        address, bar, excerpt = line.partition('|')
        match = _ADDRESS.search(address)
        if bar and match and excerpt.strip():
            written[_key(match.group())] = excerpt.strip()
    return {**cited, **written}


def _key(url: str) -> str:
    return url.strip().rstrip('/')


def _add(spent: dict[str, int], usage: Mapping[str, Any]) -> None:
    for name in (
        'input_tokens',
        'cache_read_input_tokens',
        'cache_creation_input_tokens',
        'output_tokens',
    ):
        spent[name] = spent.get(name, 0) + int(usage.get(name) or 0)
    searches = (usage.get('server_tool_use') or {}).get('web_search_requests')
    spent['searches'] = spent.get('searches', 0) + int(searches or 0)


def _usage(
    spent: Mapping[str, int],
    model: str,
    latency_ms: int,
    search_usd: float,
    prices: Prices,
) -> dict[str, Any]:
    """Ce que la recherche a coûté : les jetons du petit appel au prix du
    catalogue, plus le prix fixe de chaque recherche faite. Sans prix
    connu pour le modèle, le coût reste inconnu (``None``)."""
    fresh = spent.get('input_tokens', 0)
    read = spent.get('cache_read_input_tokens', 0)
    written = spent.get('cache_creation_input_tokens', 0)
    out = spent.get('output_tokens', 0)
    cost = _cost(prices(model), fresh, read, written, out)
    if cost is not None:
        cost += spent.get('searches', 0) * search_usd
    return {
        'model': model,
        'tokens_in': fresh + read + written,
        'tokens_out': out,
        'cached_tokens': read,
        'cache_write_tokens': written,
        'latency_ms': latency_ms,
        'cost_usd': cost,
    }


def _note_usage(
    conn: sqlite3.Connection, inv: str, usage: Mapping[str, Any]
) -> None:
    """Note la dépense de la recherche, au nom de l'invocation qui cherche
    et de sa tâche en cours (une file ne fait tourner qu'une tâche à la
    fois ; une invocation en mission n'a pas de tâche à elle)."""
    task = conn.execute(
        "SELECT id FROM tasks WHERE invocation_id=? AND status='running'"
        ' ORDER BY started_at DESC LIMIT 1',
        (inv,),
    ).fetchone()
    conn.execute(
        'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, cost_usd, task_id, created_at, provider,'
        ' cached_tokens, cache_write_tokens) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            inv,
            TIER,
            usage['model'],
            usage['tokens_in'],
            usage['tokens_out'],
            usage['latency_ms'],
            'ok',
            usage['cost_usd'],
            str(task[0]) if task else '',
            utcnow(),
            PROVIDER,
            usage['cached_tokens'],
            usage['cache_write_tokens'],
        ),
    )
    conn.commit()
