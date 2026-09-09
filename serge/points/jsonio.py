#!/usr/bin/env python3
"""IO JSON des points LLM-1/LLM-B : extraction + recalls bornés (P3).

Contrat P3 : output structuré (enum fermé + `requested`). Réponse malformée
= recall avec consigne de réparation (N en policy, jamais de retry aveugle :
on change le message). Fallback runtime (killed/budget/error) = pas de
recall, le point bascule sur son repli dét.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from serge.llm.client import ChatResult
from serge.llm.runtime import RunResult, run_registered_point

REPAIR_SUFFIX = (
    ' Ta réponse précédente n\u2019était pas du JSON valide conforme au'
    ' schéma. Réponds UNIQUEMENT avec l\u2019objet JSON demandé, sans'
    ' markdown, sans commentaire.'
)


def extract_json(text: str) -> dict[str, Any] | None:
    """Extrait le premier objet JSON d'un texte (tolère le blabla autour).

    Args:
        text: Réponse brute du modèle.

    Returns:
        L'objet parsé, ou None si aucun JSON valide.
    """
    raw = (text or '').strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        pass
    start = raw.find('{')
    end = raw.rfind('}')
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def run_json(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    point_name: str,
    messages: list[dict[str, Any]],
    validate: Callable[[dict[str, Any]], bool],
    *,
    root: Path | None = None,
    caller: Callable[..., ChatResult] | None = None,
    max_tokens: int = 800,
) -> tuple[dict[str, Any] | None, RunResult | None]:
    """Appelle un point + parse JSON avec recalls bornés.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (quotas.llm_recalls_json).
        point_name: Nom registre.
        messages: Messages chat.
        validate: Prédicat sur l'objet parsé (schéma du point).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).
        max_tokens: Cap réponse.

    Returns:
        Tuple (objet validé ou None, dernier RunResult ou None).
    """
    quotas = policy.get('quotas') or {}
    try:
        recalls = int(quotas.get('llm_recalls_json', 2))
    except (TypeError, ValueError):
        recalls = 2
    attempts = [messages]
    last: RunResult | None = None
    for attempt in range(max(0, recalls) + 1):
        kwargs: dict[str, Any] = {'root': root, 'max_tokens': max_tokens}
        if caller is not None:
            kwargs['caller'] = caller
        last = run_registered_point(
            conn, policy, point_name, attempts[attempt], **kwargs
        )
        if not last.ok:
            return None, last
        data = extract_json(last.text)
        if data is not None and validate(data):
            return data, last
        repaired = [dict(item) for item in messages]
        repaired.append({'role': 'user', 'content': REPAIR_SUFFIX})
        attempts.append(repaired)
    return None, last
