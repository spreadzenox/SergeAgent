#!/usr/bin/env python3
"""Couche A : garde-fous déterministes d'allocation (0 token, non négociables).

Planchers garantis (caller), plafonds (60 % max/canal, 30 % max non prouvé),
réserve opportunité 20 %. Proposition hors bornes = clampée + loguée.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from serge.policy import PolicyError


def _bounds(policy: Mapping[str, Any]) -> tuple[float, float, float]:
    budget = policy.get('budget') or {}
    try:
        reserve = float(budget.get('allocator_reserve_ratio', 0.20))
        max_unproven = float(budget.get('allocator_max_unproven_ratio', 0.30))
        max_single = float(
            budget.get('allocator_max_single_channel_ratio', 0.60)
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.budget.allocator_* invalide') from exc
    for value in (reserve, max_unproven, max_single):
        if not 0.0 <= value <= 1.0:
            raise PolicyError('policy.budget.allocator_* hors [0,1]')
    return reserve, max_unproven, max_single


def clamp_allocations(
    policy: Mapping[str, Any],
    allocations: Mapping[str, float],
    proven: set[str],
) -> dict[str, Any]:
    """Clampe une allocation (juge ou bandit) dans les bornes A.

    Args:
        policy: Policy (réserve + plafonds).
        allocations: Parts brutes {campaign_id: part}.
        proven: Campagnes prouvées (U3 > 0...).

    Returns:
        Dict allocations (somme = 1-réserve) + reserve + log (clamps).
    """
    reserve, max_unproven, max_single = _bounds(policy)
    ids = list(allocations)
    if not ids:
        return {'allocations': {}, 'reserve': reserve, 'log': []}
    total = sum(max(0.0, float(allocations[item])) for item in ids)
    if total <= 0:
        equal = 1.0 / len(ids)
        shares = {item: equal for item in ids}
    else:
        shares = {
            item: max(0.0, float(allocations[item])) / total for item in ids
        }
    log: list[str] = []
    for _ in range(3):
        over = {
            item: share for item, share in shares.items() if share > max_single
        }
        if not over:
            break
        for item in over:
            log.append(f'{item} : {shares[item]:.2f} → clamp {max_single:.2f}')
            shares[item] = max_single
        rest = 1.0 - sum(shares.values())
        others = [item for item in ids if item not in over]
        base = sum(shares[item] for item in others) or 1.0
        for item in others:
            shares[item] += rest * (shares[item] / base)
    unproven_total = sum(
        share for item, share in shares.items() if item not in proven
    )
    if unproven_total > max_unproven and proven:
        factor = max_unproven / unproven_total
        for item in ids:
            if item not in proven:
                old = shares[item]
                shares[item] = old * factor
                log.append(
                    f'{item} : {old:.2f} → non-prouvé {shares[item]:.2f}'
                )
        rest = 1.0 - sum(shares.values())
        base = sum(shares[item] for item in proven if item in shares) or 1.0
        for item in proven:
            if item in shares:
                shares[item] += rest * (shares[item] / base)
    scale = 1.0 - reserve
    clamped = {item: round(share * scale, 4) for item, share in shares.items()}
    return {'allocations': clamped, 'reserve': reserve, 'log': log}
