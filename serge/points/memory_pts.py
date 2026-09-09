#!/usr/bin/env python3
"""Points D1/D2 : consolidate (LLM-B, T2) + edit_serge_md (LLM-B, T1).

D1 : batch 3j → candidats leçons/playbooks/pitfalls (K max, confiance,
sources, scope). Jamais d'écriture directe (ticket MEMORY par l'appelant).
D2 : SERGE.md sous limite de lignes (diff + rollback par l'appelant).
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

SERGE_MD_SYSTEM = """Tu mets à jour SERGE.md (français) : qui, venture active, 5 leçons chaudes, 3 pièges, état chiffré du jour.
Réponds UNIQUEMENT un objet JSON : {"serge_md": "...markdown...", "changements": ["..."]}.
Contraintes : sous la limite de lignes ; diff minimale ; chiffres fournis uniquement ; jamais de secret/PII."""

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
    requested_text: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """D1 : candidats-leçons du batch (K max, écriture via ticket).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (memory.consolidate_max_items).
        episodes_text: Épisodes période (tronqué 6000c).
        other_text: Verbatims OTHER + recherches (tronqué 1500c).
        requested_text: Champs requested P3 (tronqué 800c).
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
                f'\nRequested : {requested_text[:800]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 2000}
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


def edit_serge_md(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    current_md: str,
    changes_text: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """D2 : nouvelle version SERGE.md (bornée, diff par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (memory.serge_md_max_lines).
        current_md: Version actuelle.
        changes_text: Changements depuis (tronqué 1000c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict serge_md/changements/fallback (repli = version précédente).
    """
    try:
        max_lines = int(
            (policy.get('memory') or {}).get('serge_md_max_lines', 100)
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.serge_md_max_lines invalide') from exc
    messages = [
        {'role': 'system', 'content': SERGE_MD_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'Actuel ({len(current_md.splitlines())} lignes,'
                f' max {max_lines}) :\n{current_md[:3000]}'
                f'\nChangements : {changes_text[:1000]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 2000}
    if caller is not None:
        kwargs['caller'] = caller

    def _valid(data: dict[str, Any]) -> bool:
        body = data.get('serge_md')
        if not isinstance(body, str) or not body.strip():
            return False
        if len(body.splitlines()) > max_lines:
            return False
        return isinstance(data.get('changements'), list)

    data, result = run_json(
        conn, policy, 'edit_serge_md', messages, _valid, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'serge_md': current_md,
            'changements': [],
            'fallback': reason or 'parse',
        }
    return {
        'serge_md': str(data['serge_md']),
        'changements': [str(item) for item in data['changements']],
        'fallback': '',
    }
