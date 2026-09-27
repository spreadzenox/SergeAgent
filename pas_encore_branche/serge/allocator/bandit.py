#!/usr/bin/env python3
"""Couche B : bandit Thompson Sampling (algo, 0 token, continu).

Bras = campagnes. Net = intent pondéré (barème P7) − coût (policy).
Beta(α, β) par bras, tirage, parts normalisées. Sans données =
équi-répartition. Seed injectable (tests, rejeu).
"""

from __future__ import annotations

import random
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.metrics import campaign_metrics


def _net_reward(
    conn: sqlite3.Connection, policy: Mapping[str, Any], campaign_id: str
) -> tuple[float, float]:
    metrics = campaign_metrics(conn, campaign_id)
    section = policy.get('prospection') or {}
    budget = policy.get('budget') or {}
    try:
        w_intent = float(section.get('score_w_intent', 25))
        w_reply = float(section.get('score_w_reply', 10))
        cost_w = float(budget.get('allocator_bandit_cost_per_eur', 10.0))
    except (TypeError, ValueError):
        w_intent, w_reply, cost_w = 25.0, 10.0, 10.0
    positives = w_intent * metrics['u3'] + w_reply * max(
        0, metrics['u2'] - metrics['u3']
    )
    net = positives - cost_w * metrics['cost_eur']
    return net, float(metrics['u1'])


def propose_bandit(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    venture_id: str,
    *,
    seed: int | None = None,
) -> dict[str, Any]:
    """Propose une allocation (parts 0-1 par campagne RUNNING/READY).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (barème P7 + allocator.bandit_cost_per_eur).
        venture_id: Venture scope.
        seed: Graine RNG (rejeu/tests).

    Returns:
        Dict allocations {campaign_id: part} + draws + total_net.
    """
    rows = conn.execute(
        'SELECT id FROM campaigns WHERE venture_id=?'
        " AND state IN ('RUNNING','READY') ORDER BY created_at ASC",
        (venture_id,),
    ).fetchall()
    campaigns = [str(row[0]) for row in rows]
    if not campaigns:
        return {'allocations': {}, 'draws': {}, 'total_net': 0.0}
    rng = random.Random(seed)
    draws: dict[str, float] = {}
    total_net = 0.0
    any_data = False
    for campaign_id in campaigns:
        net, u1 = _net_reward(conn, policy, campaign_id)
        total_net += net
        if u1 > 0:
            any_data = True
        alpha = 1.0 + max(0.0, net) / 10.0
        beta = 1.0 + max(0.0, -net) / 10.0 + max(0.0, u1) / 50.0
        draws[campaign_id] = rng.betavariate(alpha, beta)
    if not any_data:
        share = 1.0 / len(campaigns)
        return {
            'allocations': {item: share for item in campaigns},
            'draws': draws,
            'total_net': total_net,
        }
    total = sum(draws.values()) or 1.0
    return {
        'allocations': {
            item: round(draw / total, 4) for item, draw in draws.items()
        },
        'draws': {item: round(draw, 4) for item, draw in draws.items()},
        'total_net': round(total_net, 2),
    }
