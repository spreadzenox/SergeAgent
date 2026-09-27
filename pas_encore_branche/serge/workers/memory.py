#!/usr/bin/env python3
"""Workers memory.consolidate + memory.apply (D1/D2 → écritures validées).

Consolidate : batch si dû (ticket MEMORY + SERGE.md + FYI). Apply :
écrit les items MEMORY disposés (keep/edit → couche 3 active, drop/open
→ ignorés). Seule écriture couche 3 hors owner direct.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.memory.consolidate import run_consolidation
from serge.memory.lessons import (
    add_lesson,
    add_pitfall,
    add_playbook,
    set_lesson_status,
)
from serge.tickets import get_ticket

DECIDED = frozenset({'APPROVED', 'EXECUTED', 'CLOSED'})


def run_consolidate_worker(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item memory.consolidate (batch si dû).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy.
        item: Work_item (venture_id scope).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done (+ ticket_id, counts, due).
    """
    result = run_consolidation(
        conn,
        policy,
        venture_id=str(item.get('venture_id') or ''),
        root=root,
        caller=caller,
    )
    return {'status': 'done', **result}


def _item_payload(item: Mapping[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def run_apply(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item memory.apply (items MEMORY → couche 3).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (non lue, contrat uniforme).
        item: Work_item (payload.ticket_id requis).
        root: Inutilisé (contrat workers).
        caller: Inutilisé (zéro LLM, écritures pures).

    Returns:
        Dict status done|error (+ counts, error).
    """
    del policy, root, caller
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    ticket_id = str((payload or {}).get('ticket_id') or '')
    try:
        ticket = get_ticket(conn, ticket_id) if ticket_id else None
    except ValueError:
        ticket = None
    if ticket is None:
        return {'status': 'error', 'error': 'ticket_inconnu'}
    if ticket['type'] != 'MEMORY':
        return {'status': 'error', 'error': 'ticket_non_memory'}
    if ticket['state'] not in DECIDED:
        return {'status': 'error', 'error': 'ticket_non_decide'}
    counts = {'lessons': 0, 'playbooks': 0, 'pitfalls': 0, 'skipped': 0}
    for ticket_item in ticket['items']:
        state = str(ticket_item.get('state') or '')
        if state not in {'keep', 'edit'}:
            counts['skipped'] += 1
            continue
        data = _item_payload(ticket_item)
        kind = str(ticket_item.get('kind') or '')
        label = str(ticket_item.get('label') or '')
        if kind == 'lesson':
            lesson_id = add_lesson(
                conn,
                str(data.get('statement') or data.get('enonce') or label),
                confidence=float(data.get('confiance', 0.5)),
                scope=str(data.get('scope') or 'global'),
                sources=[str(item2) for item2 in (data.get('sources') or [])],
                created_by='consolidateur',
            )
            set_lesson_status(conn, lesson_id, 'active')
            counts['lessons'] += 1
        elif kind == 'playbook':
            add_playbook(
                conn,
                str(data.get('nom') or label),
                str(data.get('conditions') or ''),
                [str(item2) for item2 in (data.get('etapes') or [])],
            )
            counts['playbooks'] += 1
        elif kind == 'pitfall':
            add_pitfall(
                conn,
                str(data.get('enonce') or label),
                str(data.get('cout') or ''),
            )
            counts['pitfalls'] += 1
        else:
            counts['skipped'] += 1
    return {'status': 'done', **counts}
