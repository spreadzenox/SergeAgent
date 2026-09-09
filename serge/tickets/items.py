#!/usr/bin/env python3
"""Items de tickets (MEMORY, QCM) + vue assemblée (rendu bot/mirror)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.tickets.shared import TicketError, fetch_ticket, new_id


def add_item(
    connection: sqlite3.Connection,
    ticket_id: str,
    kind: str,
    label: str,
    payload: dict[str, Any] | None = None,
) -> str:
    """Ajoute un item (MEMORY : leçon ; QCM : option...)."""
    fetch_ticket(connection, ticket_id)
    item_id = new_id('ti')
    connection.execute(
        'INSERT INTO ticket_items(id, ticket_id, kind, label, state,'
        ' payload_json) VALUES(?,?,?,?,?,?)',
        (
            item_id,
            ticket_id,
            kind,
            label,
            'open',
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )
    return item_id


def set_item(
    connection: sqlite3.Connection,
    item_id: str,
    state: str,
    payload: dict[str, Any] | None = None,
) -> None:
    """Change l'état d'un item (MEMORY : keep/edit/drop...)."""
    cursor = connection.execute(
        'UPDATE ticket_items SET state=?, payload_json=? WHERE id=?',
        (state, json.dumps(payload or {}, ensure_ascii=False), item_id),
    )
    if not cursor.rowcount:
        raise TicketError(f'item inconnu : {item_id}')


def get_ticket(
    connection: sqlite3.Connection, ticket_id: str
) -> dict[str, Any]:
    """Ticket + items + événements (rendu Discord/Mission Control)."""
    ticket = dict(fetch_ticket(connection, ticket_id))
    ticket['items'] = [
        dict(item)
        for item in connection.execute(
            'SELECT id, ticket_id, kind, label, state, payload_json'
            ' FROM ticket_items WHERE ticket_id=?',
            (ticket_id,),
        )
    ]
    ticket['events'] = [
        dict(event)
        for event in connection.execute(
            'SELECT ticket_id, ts, actor, kind, payload_json'
            ' FROM ticket_events WHERE ticket_id=? ORDER BY id',
            (ticket_id,),
        )
    ]
    return ticket
