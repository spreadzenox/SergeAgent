#!/usr/bin/env python3
"""Projecteurs P5 Politique : policy générale, testing à froid, trust, réglages."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.policy_snapshots import policy_en_vigueur


def project_politique_active(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Politique actuellement chargée et validée (P5).

    Args:
        conn: Connexion canon (dernier snapshot).
        policy: Ignoré — la vérité est le snapshot.
        now: Maintenant ISO (ignoré).

    Returns:
        Dict {policy: {...}}.
    """
    _ = (policy, now)
    return {'policy': policy_en_vigueur(conn)}


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
    from kit.instance_file import _validate_testing

    live = policy_en_vigueur(conn)
    testing = live.get('testing')
    raw: dict[str, Any] = testing if isinstance(testing, dict) else {}
    testing_cfg = _validate_testing(raw)
    return {
        'running_campaigns': int(running),
        'is_locked': locked,
        'config': testing_cfg,
    }


def project_reglages(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les réglages d'invocation et les quotas marqués « policy » (P5).

    Ils sont rangés avec l'invocation ou la table qui s'en sert, pas dans
    la policy générale ; la page Policy les montre ici, par étape puis par
    invocation, modifiables en direct.

    Returns:
        ``{invocations: [{invocation_id, titre, etape, reglages}],
        quotas: [...]}``.
    """
    _ = (policy, now)
    groupes: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        'SELECT s.invocation_id, i.title, COALESCE(st.titre, i.step_id),'
        ' s.name, s.type, s.value, s.min_value, s.max_value, s.description'
        ' FROM invocation_settings s JOIN invocations i ON i.id=s.invocation_id'
        ' LEFT JOIN pipeline_steps st ON st.id=i.step_id'
        " WHERE s.policy=1 AND i.deleted_at=''"
        ' ORDER BY COALESCE(st.rang, 99), s.invocation_id, s.name'
    ).fetchall():
        groupe = groupes.setdefault(
            str(row[0]),
            {
                'invocation_id': str(row[0]),
                'titre': str(row[1] or row[0]),
                'etape': str(row[2] or ''),
                'reglages': [],
            },
        )
        groupe['reglages'].append(
            {
                'name': str(row[3]),
                'type': str(row[4]),
                'value': str(row[5]),
                'min': str(row[6]),
                'max': str(row[7]),
                'description': str(row[8]),
            }
        )
    quotas = [
        {
            'id': str(r[0]),
            'table': str(r[1]),
            'column': str(r[2]),
            'values': str(r[3]),
            'max': int(r[4]),
            'description': str(r[5]),
        }
        for r in conn.execute(
            'SELECT id, table_name, column_name, counted_values, max_value,'
            ' description FROM table_quotas WHERE policy=1 ORDER BY id'
        ).fetchall()
    ]
    return {'invocations': list(groupes.values()), 'quotas': quotas}
