#!/usr/bin/env python3
"""Client OpenRouter minimal : chat + usage. urllib only, erreurs typées."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'


class LlmError(ValueError):
    pass


@dataclass(frozen=True)
class ChatResult:
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int


def _usage(payload: dict[str, Any]) -> tuple[int, int]:
    usage = payload.get('usage') or {}
    try:
        return int(usage.get('prompt_tokens') or 0), int(
            usage.get('completion_tokens') or 0
        )
    except (TypeError, ValueError):
        return 0, 0


def chat(
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    referer: str = '',
    timeout: float = 60.0,
    max_tokens: int = 500,
    temperature: float = 0.3,
    base_url: str = OPENROUTER_BASE_URL,
) -> ChatResult:
    """Un chat completion + usage. Clé en header uniquement, jamais loguée.

    Args:
        api_key: Clé OpenRouter.
        model: Model id (ex. x-ai/grok-4).
        messages: Historique (role/content str ou blocs multimodaux).
        referer: HTTP-Referer de l'instance.
        timeout: Timeout HTTP (secondes).
        max_tokens: Cap réponse.
        temperature: Température.
        base_url: Base API (override tests).

    Returns:
        ChatResult (texte + tokens + modèle + latence).

    Raises:
        LlmError: AUTH (401/clé), NETWORK, API, EMPTY (sans réponse).
    """
    if not api_key or not model:
        raise LlmError('AUTH: chat needs an API key and a model')
    body = json.dumps(
        {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        }
    ).encode('utf-8')
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
        raise LlmError(f'API: OpenRouter HTTP {exc.code}') from exc
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
        text = str(choices[0]['message']['content'] or '').strip()
    except (IndexError, KeyError, TypeError, AttributeError) as exc:
        raise LlmError('EMPTY: OpenRouter empty reply') from exc
    if not text:
        raise LlmError('EMPTY: OpenRouter empty reply')
    tokens_in, tokens_out = _usage(payload)
    used_model = str(payload.get('model') or model)
    return ChatResult(
        text=text,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        model=used_model,
        latency_ms=latency_ms,
    )
