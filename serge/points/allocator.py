#!/usr/bin/env python3
"""Point A1 : judge_allocator (LLM-1, T3). Juge + bornes A + justifications.

Valide/ajuste la proposition B. Garde-fous : clamp A systématique,
revirement > 10 pts justifié, écart > 15 pts vs B justifié (sinon flag
leçon candidate), irréversibles → tickets (jamais appliqués). Repli : B.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.allocator.guards import clamp_allocations
from serge.points.jsonio import run_json

JUDGE_SYSTEM = """Tu es l'alloueur budgétaire (français). Tu reçois l'état des campagnes (U1-U5, coûts), la proposition mathématique B et les leçons.
Réponds UNIQUEMENT un objet JSON : {"allocations": {"campagne": 0.0-1.0}, "mouvements": [{"type": "lancer|pauser|kill|allouer_reserve", "cible": "...", "detail": "...", "irreversible": true|false}], "justifications": {"sujet": "1 phrase"}}.
Règles : justifie tout revirement (> 10 pts contre l'allocation précédente) en 1 phrase ; tout écart > 15 pts vs B demande une justification "ecart_bandit" étendue ; ordres irréversibles marqués irreversible=true (jamais exécutés directement)."""


def _valid_judge(data: dict[str, Any], campaigns: set[str]) -> bool:
    allocations = data.get('allocations')
    if not isinstance(allocations, dict) or not allocations:
        return False
    for key, share in allocations.items():
        if key not in campaigns:
            return False
        try:
            value = float(share)
        except (TypeError, ValueError):
            return False
        if value < 0:
            return False
    mouvements = data.get('mouvements')
    if not isinstance(mouvements, list):
        return False
    for item in mouvements:
        if not isinstance(item, dict):
            return False
        if item.get('type') not in {
            'lancer',
            'pauser',
            'kill',
            'allouer_reserve',
        }:
            return False
        if not isinstance(item.get('irreversible'), bool):
            return False
    return isinstance(data.get('justifications'), dict)


def _max_shift(
    new: Mapping[str, float], old: Mapping[str, float] | None
) -> float:
    if not old:
        return 0.0
    keys = set(new) | set(old)
    return max(
        abs(float(new.get(key, 0)) - float(old.get(key, 0))) for key in keys
    )


def judge_allocation(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    state_text: str,
    proposition_b: Mapping[str, float],
    proven: set[str],
    *,
    previous: Mapping[str, float] | None = None,
    lessons_text: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """A1 : allocation jugée (clamp A + justifs + tickets irréversible).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (bornes A + seuils justif).
        state_text: U1-U5 + coûts + contraintes (tronqué 4000c).
        proposition_b: Parts bandit {campaign_id: part}.
        proven: Campagnes prouvées.
        previous: Allocation précédente (revirements).
        lessons_text: Leçons + opportunités (tronqué 1000c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict allocations/reserve/mouvements/tickets_needed/justifications/
        ecart_non_justifie/log/fallback (repli = B clampé).
    """
    budget = policy.get('budget') or {}
    try:
        reversal_pts = float(budget.get('allocator_reversal_points', 10))
        gap_pts = float(budget.get('allocator_bandit_gap_points', 15))
    except (TypeError, ValueError):
        reversal_pts, gap_pts = 10.0, 15.0
    campaigns = set(proposition_b)
    messages = [
        {'role': 'system', 'content': JUDGE_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'État : {state_text[:4000]}'
                f'\nProposition B : {dict(proposition_b)}'
                f'\nLeçons : {lessons_text[:1000]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'judge_allocator',
        messages,
        lambda obj: _valid_judge(obj, campaigns),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        clamped = clamp_allocations(policy, dict(proposition_b), proven)
        return {
            **clamped,
            'mouvements': [],
            'tickets_needed': [],
            'justifications': {},
            'ecart_non_justifie': False,
            'fallback': reason or 'parse',
        }
    raw = {key: float(share) for key, share in data['allocations'].items()}
    clamped = clamp_allocations(policy, raw, proven)
    justifications = {
        str(key): str(value) for key, value in data['justifications'].items()
    }
    shift = _max_shift(raw, previous) * 100
    gap = _max_shift(raw, proposition_b) * 100
    revirement_ok = shift <= reversal_pts or bool(justifications)
    ecart_ok = gap <= gap_pts or 'ecart_bandit' in justifications
    if not revirement_ok:
        clamped['log'].append(f'revirement {shift:.0f}pts non justifié')
    mouvements = [
        {
            'type': str(item['type']),
            'cible': str(item.get('cible') or ''),
            'detail': str(item.get('detail') or ''),
            'irreversible': bool(item.get('irreversible')),
        }
        for item in data['mouvements']
    ]
    tickets_needed = [item for item in mouvements if item['irreversible']]
    applied = [item for item in mouvements if not item['irreversible']]
    return {
        **clamped,
        'mouvements': applied,
        'tickets_needed': tickets_needed,
        'justifications': justifications,
        'ecart_non_justifie': not ecart_ok,
        'revirement_non_justifie': not revirement_ok,
        'fallback': '',
    }
