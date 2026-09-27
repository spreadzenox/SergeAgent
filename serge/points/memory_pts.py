#!/usr/bin/env python3
"""Point D1 : consolidate (LLM-B, T2).

Batch tous les 3 jours → candidats leçons / procédures / pièges (K max,
confiance, sources, portée). Jamais d'écriture directe : l'appelant ouvre
un ticket MEMORY.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.policy import PolicyError

CONSOLIDATE_SYSTEM = """Tu distilles des épisodes en connaissances (français).
Réponds UNIQUEMENT un objet JSON : {"lecons": [{"enonce": "...", "confiance": 0.0-1.0, "sources": ["evt..."], "scope": "global|venture|canal"}], "playbooks": [{"nom": "...", "conditions": "...", "etapes": ["..."]}], "pitfalls": [{"enonce": "...", "cout": "..."}]}.
Règles : énoncés actionnables (pas de banalités) ; chaque leçon a ≥ 1 source ; anonymise la PII ; scope minimal juste."""

SCOPES = frozenset({'global', 'venture', 'canal'})


def _valid_consolidation(data: dict[str, Any], k_max: int) -> bool:
    for key in ('lecons', 'playbooks', 'pitfalls'):
        if not isinstance(data.get(key), list):
            return False
    if (
        len(data['lecons']) + len(data['playbooks']) + len(data['pitfalls'])
        > k_max
    ):
        return False
    for lesson in data['lecons']:
        if not isinstance(lesson, dict):
            return False
        if not lesson.get('enonce'):
            return False
        try:
            confiance = float(lesson.get('confiance', -1))
        except (TypeError, ValueError):
            return False
        if not 0.0 <= confiance <= 1.0:
            return False
        if not lesson.get('sources') or lesson.get('scope') not in SCOPES:
            return False
    for book in data['playbooks']:
        if not isinstance(book, dict) or not book.get('nom'):
            return False
    for pit in data['pitfalls']:
        if not isinstance(pit, dict) or not pit.get('enonce'):
            return False
    return True


def consolidate(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    episodes_text: str,
    *,
    other_text: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """D1 : candidats-leçons du batch (K max, écriture via ticket).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (memory.consolidate_max_items).
        episodes_text: Épisodes période (tronqué 6000c).
        other_text: Verbatims OTHER + recherches (tronqué 1500c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict lecons/playbooks/pitfalls/fallback (repli = vide + FYI).
    """
    try:
        k_max = int(
            (policy.get('memory') or {}).get('consolidate_max_items', 10)
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.consolidate_max_items invalide') from exc
    messages = [
        {'role': 'system', 'content': CONSOLIDATE_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'Épisodes : {episodes_text[:6000]}'
                f'\nOTHER : {other_text[:1500]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'consolidate',
        messages,
        lambda obj: _valid_consolidation(obj, k_max),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'lecons': [],
            'playbooks': [],
            'pitfalls': [],
            'fallback': reason or 'parse',
        }
    return {
        'lecons': [
            {
                'enonce': str(item['enonce']),
                'confiance': float(item['confiance']),
                'sources': [str(item2) for item2 in item['sources']],
                'scope': str(item['scope']),
            }
            for item in data['lecons']
        ],
        'playbooks': [
            {
                'nom': str(item.get('nom') or ''),
                'conditions': str(item.get('conditions') or ''),
                'etapes': [str(item2) for item2 in (item.get('etapes') or [])],
            }
            for item in data['playbooks']
        ],
        'pitfalls': [
            {
                'enonce': str(item.get('enonce') or ''),
                'cout': str(item.get('cout') or ''),
            }
            for item in data['pitfalls']
        ],
        'fallback': '',
    }
