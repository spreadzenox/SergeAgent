#!/usr/bin/env python3
"""Client OpenRouter minimal : chat + usage. urllib only, erreurs typées."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'


class LlmError(ValueError):
    pass


@dataclass(frozen=True)
class ToolCall:
    """Un outil demandé par le modèle (il n’exécute rien)."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ChatResult:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int
    tool_calls: tuple[ToolCall, ...] = ()
    # Ce qu'OpenRouter a facturé, en dollars ; None s'il ne le dit pas.
    cost_usd: float | None = None
    # Chez qui l'appel est parti (Anthropic, Google Vertex…), et combien de
    # jetons ont été lus ou écrits dans le cache.
    provider: str = ''
    cached_tokens: int = 0
    cache_write_tokens: int = 0


def _usage(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get('usage') or {}
    try:
        return int(usage.get('prompt_tokens') or 0), int(
            usage.get('completion_tokens') or 0
        )
    except (TypeError, ValueError):
        return 0, 0


def _cache(payload: Mapping[str, Any]) -> tuple[int, int]:
    """Les jetons lus et écrits dans le cache, d'après OpenRouter
    (``usage.prompt_tokens_details``) ; ``(0, 0)`` s'il ne le dit pas."""
    usage = payload.get('usage') or {}
    details = (
        usage.get('prompt_tokens_details') if isinstance(usage, dict) else {}
    )
    if not isinstance(details, dict):
        return 0, 0
    try:
        return int(details.get('cached_tokens') or 0), int(
            details.get('cache_write_tokens') or 0
        )
    except (TypeError, ValueError):
        return 0, 0


def _why_empty(payload: Mapping[str, Any]) -> str:
    """Ce qu'OpenRouter dit d'une réponse vide : la raison de la fin, le
    modèle et l'erreur du fournisseur s'il y en a une.

    Exemple : `` (fin : length ; modèle : deepseek/… ; erreur : …)``.
    """
    choices = payload.get('choices') or [{}]
    first = choices[0] if isinstance(choices[0], dict) else {}
    error = first.get('error') or payload.get('error') or {}
    parts = [
        f'fin : {first.get("finish_reason") or "?"}',
        f'modèle : {payload.get("model") or "?"}',
    ]
    native = first.get('native_finish_reason')
    if native:
        parts.append(f'fin chez le fournisseur : {native}')
    if isinstance(error, dict) and error:
        parts.append(f'erreur : {str(error.get("message") or error)[:200]}')
    message = first.get('message') if isinstance(first, dict) else None
    if isinstance(message, dict) and message.get('reasoning'):
        parts.append('réflexion rendue sans réponse')
    return ' (' + ' ; '.join(parts) + ')'


def _tool_calls(message: Mapping[str, Any]) -> tuple[ToolCall, ...]:
    raw = message.get('tool_calls') or []
    if not isinstance(raw, list):
        return ()
    out: list[ToolCall] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        fn = item.get('function') or {}
        if not isinstance(fn, dict):
            continue
        ident = str(item.get('id') or '')
        name = str(fn.get('name') or '')
        args = fn.get('arguments')
        if isinstance(args, dict):
            args = json.dumps(args, ensure_ascii=False)
        else:
            args = str(args or '')
        if ident and name:
            out.append(ToolCall(ident, name, args))
    return tuple(out)


def chat(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    referer: str = '',
    timeout: float = 60.0,
    base_url: str = OPENROUTER_BASE_URL,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool = False,
) -> ChatResult:
    """Un chat completion + usage. Clé en header uniquement, jamais loguée.

    Args:
        api_key: Clé OpenRouter.
        model: Model id (ex. x-ai/grok-4).
        messages: Historique (role/content str ou blocs multimodaux).
        referer: HTTP-Referer de l'instance.
        timeout: Timeout HTTP (secondes).
        base_url: Base API (override tests).
        tools: Schémas OpenAI (renvoyés à chaque tour).
        tool_choice: ``auto`` / ``none`` / forcer un outil.
        parallel_tool_calls: Plusieurs outils d’un coup (défaut : non).

    Returns:
        ChatResult (texte et/ou tool_calls + tokens + modèle + latence).

    Raises:
        LlmError: AUTH (401/clé), NETWORK, API, EMPTY (sans réponse).
    """
    if not api_key or not model:
        raise LlmError('AUTH: chat needs an API key and a model')
    # Pas de température : celle du fournisseur, le prompt fait le reste
    # (décisions Q62 et Q68).
    payload: dict[str, Any] = {'model': model, 'messages': messages}
    if tools:
        payload['tools'] = tools
        payload['parallel_tool_calls'] = parallel_tool_calls
        if tool_choice is not None:
            payload['tool_choice'] = tool_choice
    if _keeps_cache(model, messages, tool_choice):
        payload['cache_control'] = {'type': 'ephemeral'}
    if model.lstrip('~').startswith('anthropic/'):
        # Le cache est propre à chaque fournisseur : réparti entre Anthropic,
        # Google Vertex et Amazon Bedrock, un appel sur deux le ratait et
        # coûtait dix fois plus (une construction à 17 $ au lieu de 4 $, le
        # 15 novembre 2026). Anthropic d'abord, les autres seulement s'il
        # ne répond pas.
        payload['provider'] = {'order': ['anthropic'], 'allow_fallbacks': True}
    body = json.dumps(payload).encode('utf-8')
    headers = {'Content-Type': 'application/json'}
    headers['Authorization'] = f'Bearer {api_key}'
    if referer:
        headers['HTTP-Referer'] = referer
        headers['X-Title'] = 'Serge runtime'
    request = urllib.request.Request(
        f'{base_url.rstrip("/")}/chat/completions',
        data=body,
        headers=headers,
        method='POST',
    )
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise LlmError('AUTH: OpenRouter key rejected') from exc
        raison = _raison_http(exc)
        if exc.code == 402:
            raise LlmError(
                'CREDIT: OpenRouter HTTP 402, plus de crédit sur le compte ou'
                f' la clé{raison}'
            ) from exc
        raise LlmError(f'API: OpenRouter HTTP {exc.code}{raison}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise LlmError(f'NETWORK: OpenRouter unreachable ({exc})') from exc
    latency_ms = int((time.monotonic() - started) * 1000)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LlmError('API: OpenRouter invalid JSON') from exc
    if not isinstance(payload, dict):
        raise LlmError('API: OpenRouter unexpected response')
    try:
        choices = payload.get('choices') or []
        message = choices[0]['message']
        if not isinstance(message, dict):
            raise TypeError('message')
        text = str(message.get('content') or '').strip()
        calls = _tool_calls(message)
    except (IndexError, KeyError, TypeError, AttributeError) as exc:
        raise LlmError(
            f'EMPTY: OpenRouter empty reply{_why_empty(payload)}'
        ) from exc
    if not text and not calls:
        raise LlmError(f'EMPTY: OpenRouter empty reply{_why_empty(payload)}')
    tokens_in, tokens_out = _usage(payload)
    lus, ecrits = _cache(payload)
    used_model = str(payload.get('model') or model)
    return ChatResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=used_model,
        latency_ms=latency_ms,
        tool_calls=calls,
        cost_usd=_cost(payload),
        provider=str(payload.get('provider') or ''),
        cached_tokens=lus,
        cache_write_tokens=ecrits,
    )


def _raison_http(exc: urllib.error.HTTPError) -> str:
    """Ce qu'OpenRouter dit d'une erreur (``error.message``), en clair :
    `` : Insufficient credits…``, ou ``''``. Jamais de secret : la clé
    n'est que dans l'en-tête de la requête."""
    try:
        corps = json.loads(exc.read().decode('utf-8', 'replace') or '{}')
    except (OSError, ValueError, AttributeError):
        return ''
    erreur = corps.get('error') if isinstance(corps, dict) else None
    message = erreur.get('message') if isinstance(erreur, dict) else erreur
    # « Provider returned error » : la vraie raison est celle du fournisseur
    # (exemple : un nom de paramètre d'outil refusé par Anthropic).
    meta = erreur.get('metadata') if isinstance(erreur, dict) else None
    brut = meta.get('raw') if isinstance(meta, dict) else ''
    if brut:
        message = f'{message} : {brut}'
    return f' : {str(message)[:400]}' if message else ''


def _keeps_cache(
    model: str,
    messages: list[dict[str, Any]],
    tool_choice: str | dict[str, Any] | None,
) -> bool:
    """Faut-il demander à OpenRouter de garder l'historique en cache ?

    Les modèles d'Anthropic n'ont pas de cache automatique : il faut le
    demander, avec ``cache_control`` au niveau de la requête (OpenRouter pose
    alors lui-même le repère sur le dernier bloc, et le fait avancer à chaque
    tour). Lire en cache coûte dix fois moins (0,20 $/M au lieu de 2 $/M pour
    claude-sonnet-5.5), écrire coûte 25 % de plus. On ne le demande donc que
    dans une boucle d'outils, quand l'historique contient déjà des résultats
    d'outils et va être renvoyé encore : le gain commence au troisième appel
    d'une conversation, un ou deux appels coûteraient un peu plus.

    Les autres fournisseurs (OpenAI, DeepSeek, Gemini, Z.ai) cachent seuls.
    Une réponse finale forcée (``tool_choice`` à ``none``) n'en demande pas :
    changer ``tool_choice`` peut rendre le cache des messages inutilisable.

    raccourci : décidé sur le préfixe du modèle, non vérifié sur un vrai
    appel ; le coût de chaque appel noté dans ``llm_usage`` dit si ça marche
    (il doit cesser de croître à chaque tour).
    """
    return (
        model.lstrip('~').startswith('anthropic/')
        and tool_choice != 'none'
        and any(m.get('role') == 'tool' for m in messages)
    )


def _cost(payload: Mapping[str, Any]) -> float | None:
    """Le coût d'un appel, tel qu'OpenRouter le donne (``usage.cost``).

    OpenRouter le rend toujours, en crédits (des dollars). ``None`` si la
    réponse n'en contient pas : la dépense sera estimée par les jetons.
    """
    usage = payload.get('usage') or {}
    cost = usage.get('cost') if isinstance(usage, Mapping) else None
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        return None
    return float(cost)
