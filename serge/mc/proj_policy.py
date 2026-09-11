#!/usr/bin/env python3
"""Projecteurs P5 Politique : politique active, snapshots, testing à froid, candidats trust."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.policy_snapshots import list_snapshots


def project_politique_active(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Politique actuellement chargée et validée (P5).

    Args:
        conn: Connexion canon (ignorée, uniformité).
        policy: Policy injectée (runtime).
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {policy: {...}}.
    """
    _ = (conn, now)
    return {'policy': dict(policy)}


def project_policy_snapshots(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Historique des 20 derniers snapshots de politique (P5).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {snapshots: [...]}.
    """
    _ = (policy, now)
    return {'snapshots': list_snapshots(conn, limit=20)}


def project_testing_froid(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """État du testing à froid (E3) et présence de campagnes actives (lock).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {running_campaigns, is_locked, config}.
    """
    _ = (policy, now)
    running = conn.execute(
        "SELECT COUNT(*) FROM campaigns WHERE state='RUNNING'"
    ).fetchone()[0]
    locked = int(running) > 0
    # On lit le testing par défaut ou courant
    from kit.instance_file import _validate_testing

    testing_cfg = _validate_testing({})
    return {
        'running_campaigns': int(running),
        'is_locked': locked,
        'config': testing_cfg,
    }


def project_trust_candidates(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Types de tickets éligibles à l'auto-approbation (>95% sur >=20 tickets).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (seuils tickets.trust_min_approvals / trust_min_rate).
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {candidates: [{type, total, approved, rate, threshold_rate, eligible}]}.
    """
    _ = now
    t_cfg = policy.get('tickets') or {}
    min_appr = int(t_cfg.get('trust_min_approvals', 20))
    min_rate = float(t_cfg.get('trust_min_rate', 0.95))

    rows = conn.execute(
        'SELECT t.type, te.kind, COUNT(*) FROM ticket_events te'
        ' JOIN tickets t ON t.id=te.ticket_id WHERE te.kind IN'
        " ('transition.approved','transition.rejected')"
        ' GROUP BY t.type, te.kind'
    ).fetchall()

    comptes: dict[str, dict[str, int]] = {}
    for r in rows:
        typ = str(r[0])
        kind = str(r[1])
        c = int(r[2])
        comptes.setdefault(typ, {})[kind] = c

    candidats = []
    for typ in sorted(comptes.keys()):
        appr = comptes[typ].get('transition.approved', 0)
        rej = comptes[typ].get('transition.rejected', 0)
        tot = appr + rej
        rate = appr / tot if tot > 0 else 0.0
        eligible = tot >= min_appr and rate >= min_rate
        candidats.append(
            {
                'type': typ,
                'total': tot,
                'approved': appr,
                'rate': round(rate, 4),
                'threshold_rate': min_rate,
                'threshold_min': min_appr,
                'eligible': eligible,
            }
        )

    return {'candidates': candidats}
