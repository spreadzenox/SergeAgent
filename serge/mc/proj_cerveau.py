#!/usr/bin/env python3
"""Projecteurs P2 Cerveau : signaux, décisions, pensées, invocations.

Lecture seule. Allumer ou éteindre une invocation passe par le
coupe-circuit (``/owner/api/coupe``, cible ``invocation``).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_etape import lister_invocations
from serge.mc.proj_outils import avant_iso


def project_signaux(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Signaux entrants : les 30 derniers messages reçus, avec ce qu'en a dit
    « Traiter une réponse » (P2 signaux).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{channel, reaction, rattache, contact, contact_id,
        ts}]}.
    """
    _ = (policy, now)
    items = []
    for row in conn.execute(
        'SELECT i.channel, i.status, i.reaction, i.address, i.contact_id,'
        ' c.display, i.received_at'
        ' FROM inbound_events i LEFT JOIN contacts c ON c.id=i.contact_id'
        ' ORDER BY i.received_at DESC, i.id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'channel': str(row[0]),
                'reaction': str(row[2]),
                'rattache': row[1] != 'unattached',
                'contact': str(row[5] or row[3] or ''),
                'contact_id': str(row[4]),
                'ts': str(row[6]),
            }
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


def project_matrice(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Toutes les invocations en base, avec leur usage des 7 derniers jours.

    Args:
        conn: Connexion à la base (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        ``{points: [{nom, titre, tier, type, enabled, file, priorite,
        etape, appels_7j, tokens_7j, latence_ms, verdicts}]}``, dans
        l'ordre des étapes, puis des liens.
    """
    _ = policy
    depuis = avant_iso(now, hours=24 * 7)
    usage: dict[str, list[int]] = {}
    verdicts: dict[str, dict[str, int]] = {}
    for nom, verdict, appels, tokens, latence in conn.execute(
        'SELECT point, verdict, COUNT(*), SUM(tokens_in + tokens_out),'
        ' SUM(latency_ms) FROM llm_usage WHERE created_at>=?'
        ' GROUP BY point, verdict',
        (depuis,),
    ).fetchall():
        total = usage.setdefault(str(nom), [0, 0, 0])
        total[0] += int(appels)
        total[1] += int(tokens or 0)
        total[2] += int(latence or 0)
        verdicts.setdefault(str(nom), {})[str(verdict)] = int(appels)
    ordre: dict[str, tuple[int, int]] = {}
    for rang, (etape,) in enumerate(
        conn.execute('SELECT id FROM pipeline_steps ORDER BY rang, id')
    ):
        for place, ligne in enumerate(lister_invocations(conn, str(etape))):
            ordre[ligne['id']] = (rang, place)
    points = []
    rows = conn.execute(
        'SELECT id, title, model_tier, type, enabled, queue_id, priority,'
        " step_id FROM invocations WHERE deleted_at='' ORDER BY id"
    ).fetchall()
    rows = sorted(rows, key=lambda r: ordre.get(str(r[0]), (99, 0)))
    for row in rows:
        nom = str(row[0])
        appels, tokens, latence = usage.get(nom, [0, 0, 0])
        points.append(
            {
                'nom': nom,
                'titre': str(row[1] or nom),
                'tier': str(row[2] or '—'),
                'type': str(row[3]),
                'enabled': bool(row[4]),
                'file': str(row[5]),
                'priorite': int(row[6]),
                'etape': str(row[7]),
                'appels_7j': appels,
                'tokens_7j': tokens,
                'latence_ms': round(latence / appels) if appels else 0,
                'verdicts': verdicts.get(nom, {}),
            }
        )
    return {'points': points}
