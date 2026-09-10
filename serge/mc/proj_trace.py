#!/usr/bin/env python3
"""Trace d'exécution : fiche work_item + contexte (timeline §10, lot 3d)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any


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
        " WHERE json_extract(payload_json,'$.id')=? ORDER BY id DESC",
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
    """Fiche exécution + contexte venture/ticket/contact (lot 3d).

    Args:
        conn: Connexion canon (lecture).
        item_id: Id du work_item ('', inconnu -> None).

    Returns:
        Dict {item, note, ticket, contact, evenements} ou None.
        Chaînage causal fin différé (llm_usage sans task_id — D12).
    """
    if not item_id:
        return None
    row = conn.execute(
        'SELECT id, kind, venture_id, campaign_id, contact_id, ticket_id,'
        ' status, priority, payload_json, blocked_until, attempts,'
        ' created_at, updated_at FROM work_items WHERE id=?',
        (item_id,),
    ).fetchone()
    if row is None:
        return None
    payload = _payload_json(row[8])
    result = payload.get('result')
    note = ''
    if isinstance(result, dict):
        note = str(result.get('note') or '')
    item = {
        'id': row[0],
        'kind': row[1],
        'venture_id': row[2],
        'campaign_id': row[3],
        'contact_id': row[4],
        'ticket_id': row[5],
        'statut': row[6],
        'attempts': row[10],
        'created_at': row[11],
        'updated_at': row[12],
    }
    ticket = None
    if item['ticket_id']:
        found = conn.execute(
            'SELECT id, type, title, state FROM tickets WHERE id=?',
            (item['ticket_id'],),
        ).fetchone()
        if found is not None:
            ticket = {
                'id': found[0],
                'type': found[1],
                'titre': found[2],
                'etat': found[3],
            }
    contact = None
    if item['contact_id']:
        found = conn.execute(
            'SELECT display, email FROM contacts WHERE id=?',
            (item['contact_id'],),
        ).fetchone()
        if found is not None:
            contact = {'display': found[0], 'email': found[1]}
    return {
        'item': item,
        'note': note,
        'ticket': ticket,
        'contact': contact,
        'evenements': _item_events(conn, item_id, str(item['venture_id'])),
    }
