#!/usr/bin/env python3
"""Workers de l'étape 1 : listen.collect et listen.business_cycle.

Collect : flux RSS → pages dédupliquées (erreurs par flux, jamais fatal).
Cycle : deux découvertes indépendantes, puis choix des business à tester
avec veto déterministe.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.db.store import append_event, utcnow
from serge.listen.collectors import ListenError, fetch_rss
from serge.listen.memory import save_candidates, select_poc
from serge.listen.store import save_docs
from serge.points.listen_pts import choose_poc, discover_needs


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
    guide, needs_target, business_target = (
        str(row[0]),
        int(row[1]),
        int(row[2]),
    )
    now = utcnow()
    conn.execute(
        "UPDATE listen_cycles SET status='RUNNING', started_at=? WHERE id=?",
        (now, cycle_id),
    )
    # Les deux appels partagent uniquement cycle_id + guide. Rien n'est écrit
    # avant que les deux réponses soient revenues.
    result_a, run_a = discover_needs(
        conn,
        policy,
        'listen_discover_needs_a',
        cycle_id,
        guide,
        root=root,
        caller=caller,
    )
    result_b, run_b = discover_needs(
        conn,
        policy,
        'listen_discover_needs_b',
        cycle_id,
        guide,
        root=root,
        caller=caller,
    )
    saved_a = save_candidates(conn, cycle_id, result_a, max_items=needs_target)
    saved_b = save_candidates(conn, cycle_id, result_b, max_items=needs_target)
    result_choice, run_choice = choose_poc(
        conn, policy, cycle_id, business_target, root=root, caller=caller
    )
    selected = select_poc(conn, cycle_id, result_choice, business_target)
    status = 'DONE' if run_choice is not None and run_choice.ok else 'DEGRADED'
    conn.execute(
        'UPDATE listen_cycles SET status=?, finished_at=? WHERE id=?',
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
