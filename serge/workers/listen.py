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

from serge.listen.cluster import cluster_docs, hot_clusters
from serge.listen.collectors import ListenError, fetch_rss
from serge.listen.store import docs_in_cluster, save_docs, set_cluster
from serge.listen.store import unclustered as pending_docs
from serge.memory.summaries import put_summary
from serge.points.listen_pts import label_clusters
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
