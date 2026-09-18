#!/usr/bin/env python3
"""Boucle d’outils générique : le modèle propose, l’hôte exécute.

Un tour = une réponse modèle qui demande au moins un outil, puis les
résultats `role:tool`. Plafond global (12) + quotas couple optionnels.
Après le dernier tour d’outils : un generate forcé (`tool_choice=none`).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

from serge.llm.client import ChatResult, ToolCall
from serge.llm.outils_exec import (
    CLE_QUOTAS,
    HANDLERS,
    ContexteOutil,
    outils_pressables,
    payload_quotas,
    peut_appeler,
    restants_par_outil,
    schemas_openai,
    tours_max,
)

CLE_PERMISSIONS = 'serge_db_permissions'


def _args_norm(raw: str) -> str:
    try:
        parsed = json.loads(raw or '{}')
    except json.JSONDecodeError:
        return raw
    if not isinstance(parsed, dict):
        return raw
    return json.dumps(parsed, sort_keys=True, ensure_ascii=False)


def _refus(code: str, detail: str = '') -> dict[str, Any]:
    body: dict[str, Any] = {'ok': False, 'code': code}
    if detail:
        body['detail'] = detail
    return body


def _executer_un(
    call: ToolCall,
    ctx: ContexteOutil,
    pressables: tuple[str, ...],
    spent: dict[str, int],
    deja: set[tuple[str, str]],
) -> dict[str, Any]:
    arguments = _args_norm(call.arguments)
    code = peut_appeler(
        call.name,
        pressables=pressables,
        spent=spent,
        spec=ctx.spec,
        policy=ctx.policy,
        deja=deja,
        arguments=arguments,
    )
    if code:
        return _refus(code)
    handler = HANDLERS.get(call.name)
    if handler is None:
        return _refus('inconnu')
    try:
        parsed = json.loads(call.arguments or '{}')
    except json.JSONDecodeError:
        return _refus('invalide', 'arguments JSON illisibles')
    if not isinstance(parsed, dict):
        return _refus('invalide', 'arguments : objet attendu')
    try:
        result = handler(ctx, parsed)
    except Exception as exc:  # noqa: BLE001 — toujours un résultat outil
        return _refus('invalide', str(exc))
    if not isinstance(result, dict):
        return _refus('invalide', 'handler hors contrat')
    spent[call.name] = spent.get(call.name, 0) + 1
    deja.add((call.name, arguments))
    return result


def _est_message_quotas(item: Mapping[str, Any]) -> bool:
    if item.get('role') != 'system':
        return False
    raw = item.get('content')
    if not isinstance(raw, str):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get(CLE_QUOTAS) is True


def _injecter_quotas(
    hist: list[dict[str, Any]],
    restants: Mapping[str, int],
    tours_restants: int,
) -> None:
    """Pose ou met à jour le bloc de restants (une seule source dans hist)."""
    message = {
        'role': 'system',
        'content': json.dumps(
            payload_quotas(restants, tours_restants), ensure_ascii=False
        ),
    }
    for index, item in enumerate(hist):
        if _est_message_quotas(item):
            hist[index] = message
            return
    index = 0
    while index < len(hist) and hist[index].get('role') == 'system':
        index += 1
    hist.insert(index, message)


def _injecter_permissions(
    hist: list[dict[str, Any]], readers: tuple[str, ...]
) -> None:
    """Expose les lecteurs autorisés sans donner de SQL libre au modèle."""
    if not readers:
        return
    message = {
        'role': 'system',
        'content': json.dumps(
            {CLE_PERMISSIONS: {'readers': list(readers), 'source': 'sqlite'}},
            ensure_ascii=False,
        ),
    }
    for index, item in enumerate(hist):
        if item.get('role') != 'system':
            continue
        try:
            data = json.loads(str(item.get('content') or ''))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict) and CLE_PERMISSIONS in data:
            hist[index] = message
            return
    index = 0
    while index < len(hist) and hist[index].get('role') == 'system':
        index += 1
    hist.insert(index, message)


def _message_assistant(result: ChatResult) -> dict[str, Any]:
    calls = [
        {
            'id': item.id,
            'type': 'function',
            'function': {'name': item.name, 'arguments': item.arguments},
        }
        for item in result.tool_calls
    ]
    message: dict[str, Any] = {'role': 'assistant', 'content': result.text}
    if calls:
        message['tool_calls'] = calls
    return message


def executer_boucle(
    caller: Callable[..., ChatResult],
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    spec: Mapping[str, Any],
    policy: Mapping[str, Any],
    conn: sqlite3.Connection,
    point_name: str,
    referer: str = '',
    max_tokens: int = 800,
    temperature: float = 0.3,
) -> ChatResult:
    """Enchaîne generate → outils → generate jusqu’au texte ou au cap.

    Args:
        caller: ``chat`` ou un faux (tests). Reçoit les kwargs tools.
        api_key: Clé (vide si caller injecté).
        model: Id modèle.
        messages: Historique initial (copie interne).
        spec: Déclaration du point.
        policy: Policy (plafond tours).
        conn: Canon (handlers lecture).
        point_name: Nom du jugement (traçabilité).
        referer: HTTP-Referer.
        max_tokens: Cap par generate.
        temperature: Température.

    Returns:
        ChatResult agrégé (texte final, tokens et latence sommés).
    """
    pressables = outils_pressables(spec)
    readers = tuple(str(item) for item in (spec.get('db_readers') or ()))
    cap = tours_max(policy)
    hist = [dict(item) for item in messages]
    spent: dict[str, int] = {}
    deja: set[tuple[str, str]] = set()
    ctx = ContexteOutil(
        conn=conn, policy=policy, spec=spec, point_name=point_name
    )
    tokens_in = 0
    tokens_out = 0
    latency_ms = 0
    used_model = model
    last = ChatResult('', 0, 0, model, 0)
    tours = 0
    while True:
        tours_restants = max(0, cap - tours)
        restants = restants_par_outil(
            pressables,
            spent=spent,
            spec=spec,
            policy=policy,
            tours_faits=tours,
            tours_plafond=cap,
        )
        encore = tuple(
            ident for ident in pressables if restants.get(ident, 0) > 0
        )
        tools = schemas_openai(encore)
        if pressables:
            _injecter_quotas(hist, restants, tours_restants)
        _injecter_permissions(hist, readers)
        force_texte = not tools or tours >= cap
        last = caller(
            api_key,
            model,
            hist,
            referer=referer,
            max_tokens=max_tokens,
            temperature=temperature,
            tools=tools or None,
            tool_choice='none' if force_texte and tools else None,
        )
        tokens_in += last.tokens_in
        tokens_out += last.tokens_out
        latency_ms += last.latency_ms
        used_model = last.model or used_model
        if force_texte or not last.tool_calls:
            return ChatResult(
                last.text,
                tokens_in,
                tokens_out,
                used_model,
                latency_ms,
                (),
            )
        hist.append(_message_assistant(last))
        for call in last.tool_calls:
            body = _executer_un(call, ctx, pressables, spent, deja)
            hist.append(
                {
                    'role': 'tool',
                    'tool_call_id': call.id,
                    'content': json.dumps(body, ensure_ascii=False),
                }
            )
        tours += 1
