#!/usr/bin/env python3
"""Prévenir Julien et Clem : un ticket d'information, sans réponse attendue.

Le ticket (type ``FYI``) apparaît dans Mission Control (Décisions) et sur
Discord. Exemple : « Un contact s'est désinscrit », avec le contact, pour
qu'ils voient ce qui se passe et débloquent un cas rare.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.tickets.lifecycle import create_ticket, publish
from serge.tickets.types import ticket_types


def inform_owners(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Prévenir Julien et Clem » : ``{title, text, contact_id}``."""
    title = str(args.get('title') or '').strip()
    if not title:
        return {'ok': False, 'code': 'titre_vide'}
    contact = str(args.get('contact_id') or '')
    row = conn.execute(
        'SELECT display FROM contacts WHERE id=?', (contact,)
    ).fetchone()
    who = f'{row[0] or contact} ({contact})' if row else contact
    text = str(args.get('text') or '').strip()
    ticket_id = create_ticket(
        conn,
        ticket_types(conn),
        'FYI',
        title,
        {
            'contenu': '\n'.join(t for t in (text, who) if t),
            'contact_id': contact,
            'invocation': inv,
        },
        creator=f'invocation:{inv}',
    )
    publish(conn, ticket_id)
    return {'ok': True, 'ticket_id': ticket_id}
