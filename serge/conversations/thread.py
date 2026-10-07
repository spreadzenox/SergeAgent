#!/usr/bin/env python3
"""Le fil d'un contact : ce que Serge lui a envoyé et ce qu'il a écrit.

Tous canaux confondus, du plus ancien au plus récent (décision Q37). Seuls
les envois partis comptent : un brouillon ou un envoi annulé n'a jamais
été lu par le contact.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def contact_thread(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Lire le fil d'un contact » : ``{contact_id}``."""
    contact = str(args.get('contact_id') or '')
    rows = [
        {
            'at': str(at),
            'from': 'serge',
            'channel': str(channel),
            'kind': str(kind),
            'subject': str(subject),
            'body': str(body),
        }
        for at, channel, kind, subject, body in conn.execute(
            'SELECT sent_at, channel, kind, subject, body FROM touches'
            " WHERE contact_id=? AND status='sent'",
            (contact,),
        ).fetchall()
    ] + [
        {
            'at': str(at),
            'from': 'contact',
            'channel': str(channel),
            'id': str(ident),
            'subject': str(subject),
            'body': str(body),
            'reaction': str(reaction),
        }
        for at, channel, ident, subject, body, reaction in conn.execute(
            'SELECT received_at, channel, id, subject, body, reaction'
            ' FROM inbound_events WHERE contact_id=?',
            (contact,),
        ).fetchall()
    ]
    return {'ok': True, 'rows': sorted(rows, key=lambda r: r['at'])}
