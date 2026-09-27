#!/usr/bin/env python3
"""Trace d'exécution d'une tâche : son invocation, ses paramètres, son journal."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.funnels.contacts import address_value


def _payload_json(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw or '{}')
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _item_events(
    conn: sqlite3.Connection, item_id: str, venture_id: str
) -> list[dict[str, Any]]:
    rows = conn.execute(
        'SELECT ts, type, actor, payload_json FROM events'
        " WHERE json_extract(payload_json,'$.task')=? ORDER BY id DESC",
        (item_id,),
    ).fetchall()
    items = [
        {
            'ts': row[0],
            'type': row[1],
            'acteur': row[2],
            'extra': _payload_json(row[3]),
        }
        for row in rows
    ]
    if venture_id:
        for row in conn.execute(
            'SELECT ts, type, actor, payload_json FROM events'
            ' WHERE venture_id=? ORDER BY id DESC LIMIT 20',
            (venture_id,),
        ).fetchall():
            items.append(
                {
                    'ts': row[0],
                    'type': row[1],
                    'acteur': row[2],
                    'extra': _payload_json(row[3]),
                }
            )
    items.sort(key=lambda item: str(item['ts']), reverse=True)
    return items[:20]


def project_trace(
    conn: sqlite3.Connection, item_id: str
) -> dict[str, Any] | None:
    """Une tâche, avec le business et le contact de ses paramètres.

    Args:
        conn: Connexion à la base (lecture).
        item_id: Id de la tâche ('' ou inconnu -> None).

    Returns:
        ``{item, note, ticket, contact, evenements}`` ou None. ``note``
        porte l'erreur d'une tâche en échec ; ``evenements`` ce que la
        tâche a écrit et refusé, puis le journal du business.
    """
    if not item_id:
        return None
    row = conn.execute(
        "SELECT t.id, COALESCE(NULLIF(i.title, ''), t.invocation_id),"
        ' t.invocation_id, t.status, t.attempts, t.created_at,'
        ' t.finished_at, t.last_error, t.queue_id FROM tasks t'
        ' LEFT JOIN invocations i ON i.id=t.invocation_id WHERE t.id=?',
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    params = {
        str(name): str(value)
        for name, value in conn.execute(
            'SELECT name, value FROM task_params WHERE task_id=?', (item_id,)
        ).fetchall()
    }
    item = {
        'id': row[0],
        'kind': row[1],
        'invocation_id': row[2],
        'file': row[8],
        'venture_id': params.get('venture_id', ''),
        'contact_id': params.get('contact_id', ''),
        'statut': row[3],
        'attempts': row[4],
        'created_at': row[5],
        'updated_at': row[6],
        'params': params,
    }
    contact = None
    if item['contact_id']:
        found = conn.execute(
            'SELECT display FROM contacts WHERE id=?',
            (item['contact_id'],),
        ).fetchone()
        if found is not None:
            contact = {
                'display': found[0],
                'email': address_value(conn, item['contact_id'], 'email'),
            }
    return {
        'item': item,
        'note': str(row[7] or ''),
        'ticket': None,
        'contact': contact,
        'evenements': _item_events(conn, item_id, str(item['venture_id'])),
    }
