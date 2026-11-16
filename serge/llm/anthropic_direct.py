#!/usr/bin/env python3
"""Appeler un modèle d'Anthropic directement, sans OpenRouter.

Le réglage « Modèles d'Anthropic : appeler Anthropic directement » (page
Pipeline, famille « Appels au modèle ») envoie chez Anthropic les appels
des modèles ``anthropic/…``, avec la clé de l'instance
(``secrets/anthropic-api-key``) : l'abonnement Claude y donne du crédit
d'API pour les essais (décision Q97). Les autres modèles passent toujours par
OpenRouter.

L'interpréteur garde son historique au format d'OpenRouter ; il est
traduit ici à chaque appel. Exemples : un résultat d'outil
(``role: tool``) devient un bloc ``tool_result`` dans un message de
l'utilisateur, une capture ``image_url`` un bloc ``image``, et
``anthropic/claude-sonnet-5.5`` devient ``claude-sonnet-5-5``.

Anthropic ne donne pas le coût d'un appel : il est calculé avec ses jetons
et les prix du catalogue d'OpenRouter, qui sont ceux d'Anthropic. Exemple :
10 000 jetons lus, 90 000 relus en cache et 1 000 écrits avec Sonnet 5.5
coûtent 0,02 + 0,009 + 0,01 = 0,039 $.
"""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import anthropic

from serge.llm.client import ChatResult, LlmError, ToolCall, _keeps_cache
from serge.llm.client import chat as openrouter_chat
from serge.llm.runtime import read_api_key
from serge.paths import config_root
from serge.policy_store import policy_en_vigueur
from serge.secrets import read_secret_file

# Une réponse peut écrire un fichier entier dans un appel d'outil : la
# réponse arrive en flux, sans limite de durée de l'appel entier.
MAX_TOKENS = 64000
# Un autre modèle d'Anthropic reprend la demande si le modèle la refuse
# (classifieurs de sécurité) ; Haiku n'en a pas.
FALLBACK_BETA = 'server-side-fallback-2026-07-01'
_AVEC_RELAIS = (
    'claude-sonnet-5-5',
    'claude-opus-5',
    'claude-fable',
    'claude-mythos',
)

Prices = Callable[[str], dict[str, Any] | None]


def is_anthropic(model: str) -> bool:
    """Un modèle d'Anthropic, chez OpenRouter (``anthropic/…``)."""
    return model.lstrip('~').startswith('anthropic/')


def anthropic_model(model: str) -> str:
    """Le nom chez Anthropic : ``anthropic/claude-haiku-5.5`` →
    ``claude-haiku-5-5``."""
    return model.lstrip('~').removeprefix('anthropic/').replace('.', '-')


def caller_for(
    conn: sqlite3.Connection, model: str, root: Path | None = None
) -> tuple[Callable[..., ChatResult], str]:
    """Qui appelle le modèle, et avec quelle clé : Anthropic directement si
    le réglage le demande et que le modèle est d'Anthropic, sinon
    OpenRouter. Sans clé Anthropic, l'appel échoue et le dit.

    Une clé qui vaut pour tous les workspaces du compte (celle d'un
    abonnement) doit dire lequel sert : c'est le réglage « Anthropic,
    identifiant du workspace », envoyé avec chaque appel.
    """
    reglages = policy_en_vigueur(conn)['llm_calls']
    if reglages.get('anthropic_direct') == 'oui' and is_anthropic(model):
        base = root or config_root()
        cle = read_secret_file(base / 'secrets/anthropic-api-key')
        workspace = str(reglages.get('anthropic_workspace') or '').strip()
        return partial(chat, workspace_id=workspace), cle
    return openrouter_chat, read_api_key(root)


def chat(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    timeout: float = 60.0,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool = False,
    workspace_id: str = '',
    client: Any = None,
    prices: Prices | None = None,
    **_openrouter: Any,
) -> ChatResult:
    """Un appel à Anthropic, avec les paramètres du client OpenRouter.

    Args:
        api_key: Clé Anthropic (jamais écrite au journal).
        model: Le modèle chez OpenRouter (``anthropic/claude-sonnet-5.5``).
        messages: L'historique au format d'OpenRouter.
        timeout: Attente maximale entre deux morceaux de la réponse.
        tools: Schémas des outils, au format d'OpenRouter.
        tool_choice: ``none`` pour une réponse sans outil.
        parallel_tool_calls: Plusieurs outils dans le même tour.
        workspace_id: Le workspace à utiliser (``wrkspc_…``), pour une clé
            qui vaut pour tous ceux du compte ; vide sinon.
        client: Remplace le client Anthropic (tests).
        prices: Rend les prix d'un modèle (tests ; défaut : le catalogue).

    Raises:
        LlmError: AUTH, CREDIT, NETWORK, API, EMPTY, comme OpenRouter.
    """
    if not api_key and client is None:
        raise LlmError(
            'AUTH: pas de clé Anthropic (secrets/anthropic-api-key) ;'
            ' poser la clé ou couper « appeler Anthropic directement »'
        )
    system, history = translate(messages)
    params = _request(model, system, history, tools, tool_choice)
    if tools and not parallel_tool_calls and tool_choice != 'none':
        params['tool_choice']['disable_parallel_tool_use'] = True
    if _keeps_cache(model, messages, tool_choice):
        params['cache_control'] = {'type': 'ephemeral'}
    if workspace_id:
        params['workspace_id'] = workspace_id
    client = client or anthropic.Anthropic(api_key=api_key, timeout=timeout)
    started = time.monotonic()
    try:
        with client.beta.messages.stream(**params) as stream:
            message = stream.get_final_message().to_dict()
    except anthropic.APIConnectionError as exc:
        raise LlmError(f'NETWORK: Anthropic unreachable ({exc})') from exc
    except anthropic.APIStatusError as exc:
        raise _error(exc) from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    return _result(message, model, latency_ms, prices or _catalog_prices)


def translate(
    history: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """L'historique d'OpenRouter au format d'Anthropic : le prompt système
    à part, et des messages qui alternent l'utilisateur et le modèle (deux
    messages de suite du même côté sont réunis)."""
    system: list[str] = []
    out: list[dict[str, Any]] = []
    for message in history:
        role = message.get('role')
        if role == 'system':
            system.append(str(message.get('content') or ''))
            continue
        if role == 'tool':
            role = 'user'
            blocks = [
                {
                    'type': 'tool_result',
                    'tool_use_id': str(message.get('tool_call_id') or ''),
                    'content': str(message.get('content') or ''),
                }
            ]
        elif role == 'assistant':
            blocks = _blocks(message.get('content'))
            blocks += [
                {
                    'type': 'tool_use',
                    'id': str(call.get('id') or ''),
                    'name': str((call.get('function') or {}).get('name')),
                    'input': _input(
                        (call.get('function') or {}).get('arguments')
                    ),
                }
                for call in message.get('tool_calls') or []
            ]
        else:
            role = 'user'
            blocks = _blocks(message.get('content'))
        if not blocks:
            continue
        if out and out[-1]['role'] == role:
            out[-1]['content'].extend(blocks)
        else:
            out.append({'role': role, 'content': blocks})
    return '\n\n'.join(s for s in system if s), out


def _blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, str):
        return [{'type': 'text', 'text': content}] if content.strip() else []
    blocks: list[dict[str, Any]] = []
    for part in content or []:
        if not isinstance(part, dict):
            continue
        if part.get('type') == 'text' and str(part.get('text') or '').strip():
            blocks.append({'type': 'text', 'text': str(part['text'])})
        elif part.get('type') == 'image_url':
            url = str((part.get('image_url') or {}).get('url') or '')
            if url:
                blocks.append(_image(url))
    return blocks


def _image(url: str) -> dict[str, Any]:
    """Une capture ``data:image/png;base64,…`` ou une adresse d'image."""
    if url.startswith('data:') and ';base64,' in url:
        media, data = url[len('data:') :].split(';base64,', 1)
        source = {'type': 'base64', 'media_type': media, 'data': data}
    else:
        source = {'type': 'url', 'url': url}
    return {'type': 'image', 'source': source}


def _input(raw: Any) -> dict[str, Any]:
    """Les paramètres d'un appel d'outil ; ``{}`` s'ils sont illisibles
    (l'outil a alors répondu « arguments illisibles »)."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw or '{}'))
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _request(
    model: str,
    system: str,
    history: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    tool_choice: str | dict[str, Any] | None,
) -> dict[str, Any]:
    name = anthropic_model(model)
    params: dict[str, Any] = {
        'model': name,
        'max_tokens': MAX_TOKENS,
        'messages': history,
    }
    if system:
        params['system'] = system
    if tools:
        params['tools'] = [
            {
                'name': str(fn.get('name')),
                'description': str(fn.get('description') or ''),
                'input_schema': fn.get('parameters')
                or {'type': 'object', 'properties': {}},
            }
            for schema in tools
            if isinstance(fn := schema.get('function'), dict)
        ]
        params['tool_choice'] = {
            'type': 'none' if tool_choice == 'none' else 'auto'
        }
    thinking = _thinking(name)
    if thinking:
        params['thinking'] = thinking
    if name.startswith(_AVEC_RELAIS):
        params['betas'] = [FALLBACK_BETA]
        params['fallbacks'] = 'default'
    return params


def _thinking(name: str) -> dict[str, str] | None:
    """La réflexion coupée quand le modèle le permet, comme par OpenRouter
    qui ne la demande pas : Sonnet 5.5 refuse ``disabled`` et prend
    ``between_tools`` ; Opus 5.5 et Fable ne la coupent pas.

    raccourci : la réflexion d'Opus 5.5 n'est pas renvoyée au tour
    suivant (l'historique ne la garde pas) ; non essayé avec Opus.
    """
    if name.startswith(('claude-opus-5-5', 'claude-fable', 'claude-mythos')):
        return None
    if name.startswith('claude-sonnet-5-5'):
        return {'type': 'between_tools'}
    return {'type': 'disabled'}


def _result(
    message: dict[str, Any], model: str, latency_ms: int, prices: Prices
) -> ChatResult:
    """La réponse : son texte, ses appels d'outils, ses jetons et son coût.

    Si un autre modèle a repris la demande en cours de réponse (bloc
    ``fallback``), seule sa partie compte.
    """
    content = [b for b in message.get('content') or [] if isinstance(b, dict)]
    relais = [i for i, b in enumerate(content) if b.get('type') == 'fallback']
    if relais:
        content = content[relais[-1] + 1 :]
    stop = str(message.get('stop_reason') or '?')
    if stop == 'refusal':
        details = message.get('stop_details') or {}
        raise LlmError(
            f'API: Anthropic a refusé la demande (catégorie :'
            f' {details.get("category") or "?"})'
        )
    text = '\n'.join(
        str(b.get('text') or '') for b in content if b.get('type') == 'text'
    ).strip()
    calls = tuple(
        ToolCall(
            str(b.get('id')),
            str(b.get('name')),
            json.dumps(b.get('input') or {}, ensure_ascii=False),
        )
        for b in content
        if b.get('type') == 'tool_use'
    )
    used = str(message.get('model') or anthropic_model(model))
    if not text and not calls:
        raise LlmError(
            f'EMPTY: Anthropic empty reply (fin : {stop} ; modèle : {used})'
        )
    usage = message.get('usage') or {}
    fresh = int(usage.get('input_tokens') or 0)
    read = int(usage.get('cache_read_input_tokens') or 0)
    written = int(usage.get('cache_creation_input_tokens') or 0)
    out = int(usage.get('output_tokens') or 0)
    return ChatResult(
        text=text,
        tokens_in=fresh + read + written,
        tokens_out=out,
        model=f'anthropic/{used}' if used != anthropic_model(model) else model,
        latency_ms=latency_ms,
        tool_calls=calls,
        cost_usd=_cost(prices(model), fresh, read, written, out),
        provider='Anthropic (direct)',
        cached_tokens=read,
        cache_write_tokens=written,
    )


def _cost(
    price: dict[str, Any] | None, fresh: int, read: int, written: int, out: int
) -> float | None:
    """Le coût en dollars ; ``None`` sans prix (les jetons sont alors
    comptés à part, comme un appel au coût inconnu)."""
    if not price:
        return None
    prompt = float(price.get('prompt_usd') or 0)
    return (
        fresh * prompt
        + read * float(price.get('cache_read_usd') or prompt)
        + written * float(price.get('cache_write_usd') or prompt)
        + out * float(price.get('completion_usd') or 0)
    ) / 1_000_000


def _catalog_prices(model: str) -> dict[str, Any] | None:
    from serge.llm.catalog import model_prices

    return model_prices(model)


def _error(exc: anthropic.APIStatusError) -> LlmError:
    """Une erreur d'Anthropic, avec sa raison (jamais la clé)."""
    raison = str(getattr(exc, 'message', '') or exc)[:400]
    if isinstance(
        exc, anthropic.AuthenticationError | anthropic.PermissionDeniedError
    ):
        return LlmError(f'AUTH: Anthropic key rejected : {raison}')
    if 'credit balance' in raison.lower() or isinstance(
        exc, anthropic.EnforcedSpendLimitReachedError
    ):
        return LlmError(f'CREDIT: Anthropic HTTP {exc.status_code} : {raison}')
    if 'anthropic-workspace-id' in raison:
        raison += (
            ' — régler « Anthropic, identifiant du workspace » (page'
            ' Pipeline, « Appels au modèle »)'
        )
    return LlmError(f'API: Anthropic HTTP {exc.status_code} : {raison}')
