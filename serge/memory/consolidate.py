#!/usr/bin/env python3
"""Consolidation (D §8) : batch 3j, semi-interactif, jamais d'écriture directe.

Rassemble épisodes + OTHER + candidats → D1 → ticket MEMORY (garder/
modifier/jeter par item) → D2 → SERGE.md versionné + FYI. Tamponne le run
(summaries). Repli D1 vide : FYI "rien de nouveau".
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.memory.summaries import get_summary, put_summary, serge_md_text
from serge.points.memory_pts import consolidate as run_d1
from serge.points.memory_pts import edit_serge_md as run_d2
from serge.registry import load_ticket_types
from serge.tickets import add_item, create_ticket, publish


def last_run(conn: sqlite3.Connection) -> str:
    """Dernier run ('' si jamais).

    Args:
        conn: Connexion canon (lecture).

    Returns:
        ISO du dernier run ou ''.
    """
    found = get_summary(conn, 'consolidation')
    return str(found['content']) if found else ''


def due_for_consolidation(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    now: str | None = None,
) -> bool:
    """Échéance consolidation (rythme policy, défaut 3j).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (memory.consolidation_days).
        now: ISO (défaut : maintenant).

    Returns:
        True si un batch est dû.
    """
    moment = now or utcnow()
    try:
        days = int((policy.get('memory') or {}).get('consolidation_days', 3))
    except (TypeError, ValueError):
        days = 3
    previous = last_run(conn)
    if not previous:
        return True
    try:
        last = datetime.fromisoformat(previous)
        current = datetime.fromisoformat(moment)
    except ValueError:
        return True
    return current - last >= timedelta(days=max(1, days))


def gather_period(
    conn: sqlite3.Connection, since_iso: str, venture_id: str = ''
) -> dict[str, str]:
    """Rassemble la matière du batch (textes bornés).

    Args:
        conn: Connexion canon (lecture).
        since_iso: Début de période ('' = tout, cap 200).
        venture_id: Scope ('' = toutes).

    Returns:
        Dict episodes/other/candidates/standing.
    """
    clauses = ['ts>=?'] if since_iso else []
    params: list[Any] = [since_iso] if since_iso else []
    if venture_id:
        clauses.append('venture_id=?')
        params.append(venture_id)
    where = f'WHERE {" AND ".join(clauses)}' if clauses else ''
    rows = conn.execute(
        'SELECT id, ts, actor, type, payload_json FROM events'
        f' {where} ORDER BY id DESC LIMIT 200',
        params,
    ).fetchall()
    episodes = [f'- e{row[0]} [{row[3]}] {str(row[4])[:200]}' for row in rows]
    other = conn.execute(
        'SELECT id, channel, payload_json FROM inbound_events'
        " WHERE signal='OTHER' ORDER BY received_at DESC LIMIT 20"
    ).fetchall()
    others = []
    for row in other:
        try:
            text = str((json.loads(row[2] or '{}') or {}).get('text') or '')
        except (TypeError, ValueError):
            text = ''
        others.append(f'- {row[0]} [{row[1]}] : {text[:200]}')
    candidates = [
        f'- e{row[0]} : {str(row[4])[:200]}'
        for row in rows
        if str(row[3]) in {'lesson.candidate', 'alert.tech_fail_pattern'}
    ]
    standing = conn.execute(
        'SELECT venue, handle, warnings, status FROM accounts_standing'
        ' WHERE warnings>0 OR status<>? LIMIT 20',
        ('active',),
    ).fetchall()
    losses = [
        f'- {row[0]}/{row[1]} : {row[2]} avertissements ({row[3]})'
        for row in standing
    ]
    return {
        'episodes': '\n'.join(episodes)[:6000],
        'other': '\n'.join(others)[:1500],
        'candidates': '\n'.join(candidates)[:1500],
        'standing': '\n'.join(losses)[:800],
    }


def run_consolidation(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    *,
    venture_id: str = '',
    root: Path | None = None,
    caller: Any = None,
    now: str | None = None,
) -> dict[str, Any]:
    """Exécute un batch (dû requis) : D1 → MEMORY, D2 → SERGE.md + FYI.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy.
        venture_id: Scope ('' = global).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).
        now: ISO (défaut : maintenant).

    Returns:
        Dict due/ticket_id/fyi_id/serge_md_version/counts/fallback.
    """
    moment = now or utcnow()
    if not due_for_consolidation(conn, policy, moment):
        return {'due': False, 'ticket_id': None, 'fallback': ''}
    types = load_ticket_types()
    matter = gather_period(conn, last_run(conn), venture_id)
    candidates = run_d1(
        conn,
        policy,
        matter['episodes'],
        other_text=f'{matter["other"]}\n{matter["candidates"]}\n{matter["standing"]}',
        root=root,
        caller=caller,
    )
    total = (
        len(candidates['lecons'])
        + len(candidates['playbooks'])
        + len(candidates['pitfalls'])
    )
    if total == 0 or candidates['fallback']:
        fyi_id = create_ticket(
            conn,
            types,
            'FYI',
            'Consolidation : rien de nouveau',
            {'contenu': f'Batch {moment[:10]} : aucune leçon candidate.'},
        )
        publish(conn, fyi_id)
        put_summary(conn, 'consolidation', moment)
        return {
            'due': True,
            'ticket_id': None,
            'fyi_id': fyi_id,
            'serge_md_version': None,
            'counts': {'lecons': 0, 'playbooks': 0, 'pitfalls': 0},
            'fallback': candidates['fallback'] or 'vide',
        }
    ticket_id = create_ticket(
        conn,
        types,
        'MEMORY',
        f'Consolidation : {total} leçons à disposer',
        {'lecons': [item['enonce'][:120] for item in candidates['lecons']]},
    )
    for item in candidates['lecons']:
        add_item(
            conn,
            ticket_id,
            'lesson',
            str(item['enonce'])[:120],
            {
                'enonce': item['enonce'],
                'confiance': item['confiance'],
                'sources': item['sources'],
                'scope': item['scope'],
            },
        )
    for item in candidates['playbooks']:
        add_item(
            conn,
            ticket_id,
            'playbook',
            str(item['nom'])[:120],
            {
                'nom': item['nom'],
                'conditions': item['conditions'],
                'etapes': item['etapes'],
            },
        )
    for item in candidates['pitfalls']:
        add_item(
            conn,
            ticket_id,
            'pitfall',
            str(item['enonce'])[:120],
            {'enonce': item['enonce'], 'cout': item['cout']},
        )
    publish(conn, ticket_id)
    changes = '\n'.join(
        [f'- {item["enonce"][:100]}' for item in candidates['lecons'][:5]]
    )
    edited = run_d2(
        conn, policy, serge_md_text(conn), changes, root=root, caller=caller
    )
    version = None
    if not edited['fallback']:
        version = put_summary(conn, 'serge_md', edited['serge_md'])['version']
    fyi_id = create_ticket(
        conn,
        types,
        'FYI',
        'SERGE.md mis à jour',
        {'contenu': '\n'.join(edited['changements'][:10]) or '(inchangé)'},
    )
    publish(conn, fyi_id)
    put_summary(conn, 'consolidation', moment)
    return {
        'due': True,
        'ticket_id': ticket_id,
        'fyi_id': fyi_id,
        'serge_md_version': version,
        'counts': {
            'lecons': len(candidates['lecons']),
            'playbooks': len(candidates['playbooks']),
            'pitfalls': len(candidates['pitfalls']),
        },
        'fallback': '',
    }
