#!/usr/bin/env python3
"""Point C1 : draft_price (LLM-L, T2). Proposition prix + bornes dét.

Bornes policy vérifiées avant ticket (rejet dét si hors bornes).
Anti-garantie ("garantit X ventes" → rejet). Ticket VETO_AMONT par
l'appelant (prix owné = owner). Repli : QNA + données brutes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json
from serge.points.reply import engagement_hit
from serge.policy import PolicyError

PRICE_SYSTEM = """Tu proposes un prix (français), avec incertitude assumée.
Réponds UNIQUEMENT un objet JSON : {"prix": 0.0, "alternatives": [0.0, 0.0], "justification": "...", "risques": ["..."], "conditions_revision": "..."}.
Règles : prix et alternatives = nombres (EUR) ; justification avec benchmarks/coûts fournis ; jamais de garantie de ventes ; conditions de révision explicites (jamais définitif)."""


def _valid_price(data: dict[str, Any]) -> bool:
    try:
        prix = float(data.get('prix', -1))
        alternatives = data.get('alternatives')
    except (TypeError, ValueError):
        return False
    if prix <= 0 or not isinstance(alternatives, list):
        return False
    if len(alternatives) != 2:
        return False
    try:
        if any(float(item) <= 0 for item in alternatives):
            return False
    except (TypeError, ValueError):
        return False
    if (
        not isinstance(data.get('justification'), str)
        or not data['justification'].strip()
    ):
        return False
    if not isinstance(data.get('risques'), list):
        return False
    return isinstance(data.get('conditions_revision'), str) and bool(
        data['conditions_revision'].strip()
    )


def draft_price(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    offre_text: str,
    benchmarks_text: str = '',
    couts_text: str = '',
    objections_text: str = '',
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """C1 : proposition de prix (bornes dét, ticket par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (collect.draft_price_min/max_eur).
        offre_text: Offre (tronquée 600c).
        benchmarks_text: Benchmarks segment (tronqué 1000c).
        couts_text: Coûts unitaires (tronqué 300c).
        objections_text: Objections prix (tronqué 800c).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict proposition/action (propose|qna_brut)/reason/fallback.
    """
    section = policy.get('collect') or {}
    try:
        floor = float(section.get('draft_price_min_eur', 1.0))
        cap = float(section.get('draft_price_max_eur', 100000.0))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.draft_price bornes invalides') from exc

    def _brut(reason: str) -> dict[str, Any]:
        return {
            'proposition': None,
            'action': 'qna_brut',
            'reason': reason,
            'fallback': reason,
            'raw': {
                'offre': offre_text[:600],
                'benchmarks': benchmarks_text[:1000],
                'couts': couts_text[:300],
                'objections': objections_text[:800],
            },
        }

    messages = [
        {'role': 'system', 'content': PRICE_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'Offre : {offre_text[:600]}'
                f'\nBenchmarks : {benchmarks_text[:1000]}'
                f'\nCoûts : {couts_text[:300]}'
                f'\nObjections : {objections_text[:800]}'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 800}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'draft_price', messages, _valid_price, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return _brut(reason or 'parse')
    prix = float(data['prix'])
    if not floor <= prix <= cap:
        return _brut(f'hors_bornes:{prix}')
    hit = engagement_hit(
        f'{data["justification"]} {" ".join(str(item) for item in data["risques"])}'
    )
    if hit:
        return _brut(f'engagement:{hit}')
    return {
        'proposition': {
            'prix': prix,
            'alternatives': [float(item) for item in data['alternatives']],
            'justification': str(data['justification']),
            'risques': [str(item) for item in data['risques']],
            'conditions_revision': str(data['conditions_revision']),
        },
        'action': 'propose',
        'reason': '',
        'fallback': '',
    }
