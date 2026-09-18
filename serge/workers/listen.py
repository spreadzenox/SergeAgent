#!/usr/bin/env python3
"""Workers listen.collect + listen.cluster (J0 → J1 → FYI chaud).

Collect : flux → docs dédupliqués (erreurs par flux, jamais fatal).
Cluster : non-clusterisés → groupes dét → J1 labels → chaud (seuils
policy) → FYI + résumé versionné. Batch hebdo, jamais bloquant.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.db.store import append_event, utcnow
from serge.listen.cluster import cluster_docs, hot_clusters
from serge.listen.collectors import ListenError, fetch_rss
from serge.listen.memory import save_candidates, select_poc
from serge.listen.store import docs_in_cluster, save_docs, set_cluster
from serge.listen.store import unclustered as pending_docs
from serge.memory.summaries import put_summary
from serge.points.listen_pts import choose_poc, discover_needs, label_clusters
from serge.registry import load_ticket_types
from serge.tickets import create_ticket, publish


def run_collect(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item listen.collect (flux → docs).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (non lue, contrat uniforme).
        item: Work_item (payload.feeds [{url, source}]).
        root: Inutilisé (contrat workers).
        caller: Inutilisé (zéro LLM).

    Returns:
        Dict status done (+ new, errors par flux).
    """
    del policy, root, caller
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    feeds = (payload or {}).get('feeds') or []
    if not isinstance(feeds, list):
        return {'status': 'error', 'error': 'feeds_invalides'}
    fresh = 0
    errors: list[dict[str, str]] = []
    for feed in feeds:
        if not isinstance(feed, dict):
            continue
        url, source = str(feed.get('url') or ''), str(feed.get('source') or '')
        try:
            docs = fetch_rss(url, source or url)
        except ListenError as exc:
            errors.append({'feed': source or url, 'error': str(exc)})
            continue
        fresh += save_docs(conn, docs)
    return {'status': 'done', 'new': fresh, 'errors': errors}


def run_cluster(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item listen.cluster (groupes → J1 → FYI chaud).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (seuil Jaccard + seuils chaud).
        item: Work_item (venture_id scope, optionnel).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done (+ clusters, hot, ticket_id, fallback).
    """
    try:
        threshold = float(
            (policy.get('listen') or {}).get('cluster_jaccard_min', 0.25)
        )
    except (TypeError, ValueError):
        threshold = 0.25
    docs = pending_docs(conn)
    groups = cluster_docs(docs, threshold=threshold)
    if not groups:
        return {
            'status': 'done',
            'clusters': 0,
            'hot': 0,
            'ticket_id': '',
            'fallback': '',
        }
    for group in groups:
        set_cluster(conn, group['doc_ids'], group['id'])
    batch = []
    for group in groups:
        verbatims = [
            f'{item["title"]} — {item["excerpt"]}'
            for item in docs_in_cluster(conn, group['id'])
        ]
        batch.append({'id': group['id'], 'verbatims': verbatims})
    labels = label_clusters(conn, policy, batch, root=root, caller=caller)
    put_summary(
        conn,
        'listen_clusters',
        json.dumps(labels['clusters'], ensure_ascii=False),
    )
    if labels['fallback']:
        return {
            'status': 'done',
            'clusters': len(groups),
            'hot': 0,
            'ticket_id': '',
            'fallback': labels['fallback'],
        }
    hot = hot_clusters(labels['clusters'], policy)
    ticket_id = ''
    if hot:
        lines = '\n'.join(
            f'- {item["label"]} (vol {item["volume"]}, will {item["willingness"]})'
            for item in hot
        )
        types = load_ticket_types()
        ticket_id = create_ticket(
            conn,
            types,
            'FYI',
            f'Opportunité chaude écoute ({len(hot)})',
            {'contenu': lines},
        )
        publish(conn, ticket_id)
    return {
        'status': 'done',
        'clusters': len(groups),
        'hot': len(hot),
        'ticket_id': ticket_id,
        'fallback': '',
    }


def run_business_cycle(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Lance deux découvertes indépendantes puis le choix DB-gardé."""
    payload = json.loads(item.get('payload_json') or '{}')
    cycle_id = str(payload.get('cycle_id') or '')
    if not cycle_id:
        return {'status': 'error', 'error': 'cycle_id_manquant'}
    row = conn.execute(
        'SELECT guide, needs_target, business_target FROM listen_cycles WHERE id=?',
        (cycle_id,),
    ).fetchone()
    if row is None:
        return {'status': 'error', 'error': 'cycle_inconnu'}
    guide, needs_target, business_target = str(row[0]), int(row[1]), int(row[2])
    now = utcnow()
    conn.execute(
        "UPDATE listen_cycles SET status='RUNNING', started_at=? WHERE id=?",
        (now, cycle_id),
    )
    # Les deux appels partagent uniquement cycle_id + guide. Rien n'est écrit
    # avant que les deux réponses soient revenues.
    result_a, run_a = discover_needs(
        conn, policy, 'listen_discover_needs_a', cycle_id, guide,
        root=root, caller=caller,
    )
    result_b, run_b = discover_needs(
        conn, policy, 'listen_discover_needs_b', cycle_id, guide,
        root=root, caller=caller,
    )
    saved_a = save_candidates(conn, cycle_id, result_a, max_items=needs_target)
    saved_b = save_candidates(conn, cycle_id, result_b, max_items=needs_target)
    result_choice, run_choice = choose_poc(
        conn, policy, cycle_id, business_target, root=root, caller=caller
    )
    selected = select_poc(conn, cycle_id, result_choice, business_target)
    status = 'DONE' if run_choice is not None and run_choice.ok else 'DEGRADED'
    conn.execute(
        "UPDATE listen_cycles SET status=?, finished_at=? WHERE id=?",
        (status, utcnow(), cycle_id),
    )
    append_event(
        conn,
        actor='listen.business_cycle',
        type='listen.business_cycle',
        payload={
            'cycle_id': cycle_id,
            'needs_target': needs_target,
            'business_target': business_target,
            'saved_a': saved_a,
            'saved_b': saved_b,
            'selected': selected,
            'status': status,
        },
    )
    return {
        'status': 'done',
        'cycle_id': cycle_id,
        'saved_a': saved_a,
        'saved_b': saved_b,
        'selected': selected,
        'llm': [
            bool(run_a and run_a.ok),
            bool(run_b and run_b.ok),
            bool(run_choice and run_choice.ok),
        ],
    }
