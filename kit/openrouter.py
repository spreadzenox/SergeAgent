#!/usr/bin/env python3
"""OpenRouter API helpers (stdlib only): model catalog + chat. No secrets logged."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1'
OPENROUTER_REFERER = 'https://github.com/serge-kit'

# Live Julien slots (llm-routing.json 2026-09-04): CHEAP/DEFAULT/SMART.
RECOMMENDED_TIERS = {
    't1': 'xiaomi/mimo-v2.5',
    't2': 'deepseek/deepseek-v4-flash-0731',
    't3': 'z-ai/glm-5.3-flash',
}
TIER_LABELS = {
    't1': 'T1 (rapide/économique)',
    't2': 'T2 (défaut)',
    't3': 'T3 (stratège)',
}
TIER_TO_SLOT = {'t1': 'CHEAP', 't2': 'DEFAULT', 't3': 'SMART'}


class OpenRouterError(ValueError):
    pass


def _request(
    method: str,
    url: str,
    api_key: str = '',
    payload: dict[str, Any] | None = None,
    referer: str = '',
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Low-level JSON call. API key travels only in the Authorization header."""
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f'Bearer {api_key}'
    if referer:
        headers['HTTP-Referer'] = referer
        headers['X-Title'] = 'Serge kit installer'
    data = None
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(
        url, data=data, headers=headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8')
    except urllib.error.HTTPError as exc:
        raise OpenRouterError(f'OpenRouter HTTP {exc.code}') from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise OpenRouterError(f'OpenRouter unreachable: {exc}') from exc
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OpenRouterError('OpenRouter invalid JSON') from exc
    if not isinstance(parsed, dict):
        raise OpenRouterError('OpenRouter unexpected response')
    return parsed


def fetch_models(
    api_key: str = '',
    base_url: str = OPENROUTER_BASE_URL,
    timeout: float = 20.0,
) -> list[dict[str, Any]]:
    """List OpenRouter models, normalized and sorted (recommended first).

    Args:
        api_key: Optional key (catalog is public, key improves limits).
        base_url: API base, override for tests.
        timeout: HTTP timeout in seconds.

    Returns:
        List of {id, name, context_length, prompt_usd, completion_usd}.

    Raises:
        OpenRouterError: On network, HTTP, or parse failure.
    """
    payload = _request(
        'GET', f'{base_url.rstrip("/")}/models', api_key, timeout=timeout
    )
    raw = payload.get('data')
    if not isinstance(raw, list):
        raise OpenRouterError('OpenRouter models payload invalid')
    models: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get('id'):
            continue
        pricing = item.get('pricing') or {}
        try:
            prompt = float(pricing.get('prompt') or 0.0) * 1_000_000
            completion = float(pricing.get('completion') or 0.0) * 1_000_000
        except (TypeError, ValueError):
            prompt, completion = 0.0, 0.0
        models.append(
            {
                'id': str(item['id']),
                'name': str(item.get('name') or item['id']),
                'context_length': int(item.get('context_length') or 0),
                'prompt_usd': prompt,
                'completion_usd': completion,
            }
        )
    recommended = list(RECOMMENDED_TIERS.values())

    def _rank(model: dict[str, Any]) -> tuple[int, str]:
        try:
            return (recommended.index(str(model['id'])), '')
        except ValueError:
            return (len(recommended), str(model['id']))

    models.sort(key=_rank)
    return models


def search_models(
    models: list[dict[str, Any]], query: str, limit: int = 15
) -> list[dict[str, Any]]:
    """Filter models by substring on id or name (case-insensitive).

    Args:
        models: Normalized list from fetch_models.
        query: Substring to match.
        limit: Max results returned.

    Returns:
        Matching models, catalog order preserved.
    """
    needle = query.strip().lower()
    if not needle:
        return list(models[:limit])
    return [
        model
        for model in models
        if needle in str(model['id']).lower()
        or needle in str(model['name']).lower()
    ][:limit]


def format_model_line(model: dict[str, Any]) -> str:
    """One-line display: id — $x/$y per M tokens in/out."""
    return (
        f'{model["id"]} — ${model["prompt_usd"]:.2f}/'
        f'${model["completion_usd"]:.2f} par M tokens'
    )


def chat_completion(
    api_key: str,
    model: str,
    messages: list[dict[str, str]],
    referer: str = '',
    timeout: float = 60.0,
    max_tokens: int = 500,
    temperature: float = 0.3,
) -> str:
    """One chat completion. Minimal surface for the installer guide.

    Args:
        api_key: OpenRouter key (header only, never logged).
        model: OpenRouter model id.
        messages: Chat history (role/content).
        referer: Optional HTTP referer.
        timeout: HTTP timeout in seconds.
        max_tokens: Cap on the reply.
        temperature: Sampling temperature.

    Returns:
        The assistant text (stripped).

    Raises:
        OpenRouterError: On network, HTTP, or empty reply.
    """
    if not api_key or not model:
        raise OpenRouterError('chat needs an API key and a model')
    payload = _request(
        'POST',
        f'{OPENROUTER_BASE_URL}/chat/completions',
        api_key,
        {
            'model': model,
            'messages': messages,
            'max_tokens': max_tokens,
            'temperature': temperature,
        },
        referer,
        timeout,
    )
    try:
        choices = payload.get('choices') or []
        text = choices[0]['message']['content']
    except (IndexError, KeyError, TypeError, AttributeError) as exc:
        raise OpenRouterError('OpenRouter empty reply') from exc
    text = str(text or '').strip()
    if not text:
        raise OpenRouterError('OpenRouter empty reply')
    return text
