#!/usr/bin/env python3
"""Point O4 : review_other (LLM-1, T1). Juge OTHER batch, jamais bloquant.

Entrée : batch d'items OTHER (cap policy). Sortie : reclassements
(signal + confiance) + proposition de catégorie éventuelle (→ ticket).
Repli : tout reste OTHER (compteur + alerte gérés par l'appelant).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.observe.signals import Signal
from serge.points.jsonio import run_json

SIGNALS = {item.value for item in Signal}

OTHER_SYSTEM = """Tu reclasses des événements inclassables (file OTHER) vers 8 signaux : TECH_OK, TECH_FAIL, SEEN, ENGAGED, REPLIED, INTENT, NEGATIVE, OPT_OUT (ou OTHER si vraiment inclassable).
Réponds UNIQUEMENT un objet JSON : {"reclass": [{"id": "...", "signal": "...", "confiance": 0.0-1.0}], "proposition": null ou {"nom": "...", "definition": "...", "exemples": ["..."]}}.
proposition = nouvelle catégorie candidate si un motif revient (sinon null)."""

DEFAULT_BATCH_MAX = 20


def _valid_other(data: dict[str, Any], ids: set[str]) -> bool:
    items = data.get('reclass')
    if not isinstance(items, list):
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if item.get('id') not in ids:
            return False
        if item.get('signal') not in SIGNALS:
            return False
        try:
            confiance = float(item.get('confiance', -1))
        except (TypeError, ValueError):
            return False
        if not 0.0 <= confiance <= 1.0:
            return False
    proposition = data.get('proposition')
    if proposition is not None:
        if not isinstance(proposition, dict):
            return False
        if not proposition.get('nom') or not proposition.get('definition'):
            return False
    return True


def review_other_batch(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    items: list[dict[str, Any]],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """O4 : juge un batch OTHER (reclasse + propose catégorie).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (observation.other_batch_max_items).
        items: [{id, channel, native_type, excerpt}].
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict reclass/proposition/truncated/fallback.
    """
    try:
        cap = int(
            (policy.get('observation') or {}).get(
                'other_batch_max_items', DEFAULT_BATCH_MAX
            )
        )
    except (TypeError, ValueError):
        cap = DEFAULT_BATCH_MAX
    batch = items[: max(1, cap)]
    truncated = len(items) > len(batch)
    ids = {str(item.get('id')) for item in batch}
    lines = [
        f'- {item.get("id")} [{item.get("channel")}/{item.get("native_type")}] :'
        f' {str(item.get("excerpt") or "")[:300]}'
        for item in batch
    ]
    messages = [
        {'role': 'system', 'content': OTHER_SYSTEM},
        {'role': 'user', 'content': '\n'.join(lines)},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'review_other',
        messages,
        lambda obj: _valid_other(obj, ids),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'reclass': [],
            'proposition': None,
            'truncated': truncated,
            'fallback': reason or 'parse',
        }
    return {
        'reclass': list(data['reclass']),
        'proposition': data.get('proposition'),
        'truncated': truncated,
        'fallback': '',
    }
