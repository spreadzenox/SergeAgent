#!/usr/bin/env python3
"""Désinscrire une personne : plus aucun message, sur aucun canal.

Une personne qui écrit « ne me contactez plus » ou « STOP » (décision
Q79) :

- toutes ses adresses vont dans la liste de blocage, pour tous les canaux
  (``*``) : les garde-fous refusent tout envoi vers elles ;
- toutes ses fiches, dans tous les business (les fiches qui partagent une
  de ses adresses), passent ``OPTED_OUT`` ;
- ses envois en attente sont annulés.

C'est une protection : la capacité écrit elle-même, et note chaque
changement au journal.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow
from serge.privacy import subject_hash


def unsubscribe_contact(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Désinscrire une personne partout » : ``{contact_id}``."""
    contact = str(args.get('contact_id') or '')
    now = utcnow()
    addresses = conn.execute(
        'SELECT DISTINCT channel, value_norm FROM contact_addresses'
        ' WHERE contact_id=?',
        (contact,),
    ).fetchall()
    people = {contact} | {
        str(r[0])
        for channel, value in addresses
        for r in conn.execute(
            'SELECT contact_id FROM contact_addresses'
            ' WHERE channel=? AND value_norm=?',
            (channel, value),
        ).fetchall()
    }
    for _channel, value in addresses:
        digest = subject_hash(str(value))
        conn.execute(
            'INSERT OR IGNORE INTO blocklist(id, channel, subject_hash,'
            " subject_ref, reason, added_at) VALUES(?, '*', ?, ?,"
            " 'désinscription', ?)",
            (f'stop_{digest[:16]}', digest, contact, now),
        )
    holes = ','.join('?' * len(people))
    cancelled = conn.execute(
        "UPDATE touches SET status='cancelled', last_error='désinscription',"
        f' updated_at=? WHERE contact_id IN ({holes})'
        " AND status IN ('to_write', 'pending')",
        (now, *people),
    ).rowcount
    for person, venture in conn.execute(
        f'SELECT id, venture_id FROM contacts WHERE id IN ({holes})'
        " AND funnel_state<>'OPTED_OUT'",
        tuple(people),
    ).fetchall():
        conn.execute(
            "UPDATE contacts SET funnel_state='OPTED_OUT', updated_at=?"
            ' WHERE id=?',
            (now, person),
        )
        append_event(
            conn,
            actor='conversations',
            type='contact.opted_out',
            venture_id=str(venture),
            payload={'from_contact': contact},
            rows=[('contacts', person)],
        )
    return {
        'ok': True,
        'contacts': len(people),
        'addresses': len(addresses),
        'cancelled': cancelled,
    }
