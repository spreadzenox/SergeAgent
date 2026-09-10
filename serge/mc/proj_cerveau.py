#!/usr/bin/env python3
"""Projecteurs P2 Cerveau : signaux, clusters, décisions, pensées, usage.

Lecture seule. Registre llm-points.yaml + dérives + kills = lot 6b.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_outils import avant_iso


def project_signaux(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Signaux entrants : 30 derniers classés (P2 signaux).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{channel, type, signal, classe, score,
        contact_id, ts}]}.
    """
    _ = (policy, now)
    items = []
    for row in conn.execute(
        'SELECT channel, native_type, signal, class, score, contact_id,'
        ' received_at FROM inbound_events ORDER BY received_at DESC,'
        ' id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'channel': str(row[0]),
                'type': str(row[1]),
                'signal': str(row[2]),
                'classe': str(row[3]),
                'score': float(row[4]),
                'contact_id': str(row[5]),
                'ts': str(row[6]),
            }
        )
    return {'items': items}


def project_clusters(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Clusters d'écoute chauds 24 h (P2 clusters).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, docs, dernier}]} (hors cluster exclus).
    """
    _ = policy
    depuis = avant_iso(now, hours=24)
    items = []
    for row in conn.execute(
        'SELECT cluster_id, COUNT(*) AS n, MAX(fetched_at)'
        ' FROM listen_docs WHERE fetched_at>?'
        " AND cluster_id<>'' GROUP BY cluster_id ORDER BY n DESC",
        (depuis,),
    ).fetchall():
        items.append(
            {'id': str(row[0]), 'docs': int(row[1]), 'dernier': str(row[2])}
        )
    return {'items': items}


def project_decisions(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Décisions LLM : 30 derniers appels + verdicts (P2 décisions).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{point, tier, model, tokens, latence_ms,
        verdict, ts}]}.
    """
    _ = (policy, now)
    items = []
    for row in conn.execute(
        'SELECT point, tier, model, tokens_in, tokens_out, latency_ms,'
        ' verdict, created_at FROM llm_usage ORDER BY created_at DESC,'
        ' id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'point': str(row[0]),
                'tier': str(row[1]),
                'model': str(row[2]),
                'tokens': int(row[3]) + int(row[4]),
                'latence_ms': int(row[5]),
                'verdict': str(row[6]),
                'ts': str(row[7]),
            }
        )
    return {'items': items}


def project_pensees(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Thought stream : stub fail-soft, pas d'émetteurs (P2 stream).

    Args:
        conn: Connexion canon (ignorée, uniformité).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [], source} (contrat stable pour la page).
    """
    _ = (conn, policy, now)
    return {'items': [], 'source': 'aucune (émetteurs futurs)'}


def project_usage_points(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Usage réel par point 7 j : base de la matrice (P2).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {points: [{point, appels, tokens, latence_ms,
        verdicts: {verdict: n}}]} (jointure registre au lot 6b).
    """
    _ = policy
    depuis = avant_iso(now, hours=168)
    stats: dict[str, dict[str, Any]] = {}
    for row in conn.execute(
        'SELECT point, COUNT(*), SUM(tokens_in + tokens_out),'
        ' AVG(latency_ms) FROM llm_usage WHERE created_at>?'
        ' GROUP BY point',
        (depuis,),
    ).fetchall():
        stats[str(row[0])] = {
            'appels': int(row[1]),
            'tokens': int(row[2]),
            'latence_ms': float(row[3]),
            'verdicts': {},
        }
    for row in conn.execute(
        'SELECT point, verdict, COUNT(*) FROM llm_usage'
        ' WHERE created_at>? GROUP BY point, verdict',
        (depuis,),
    ).fetchall():
        stats[str(row[0])]['verdicts'][str(row[1])] = int(row[2])
    points = [
        {'point': nom, **valeurs}
        for nom, valeurs in sorted(
            stats.items(), key=lambda kv: kv[1]['appels'], reverse=True
        )
    ]
    return {'points': points}
