#!/usr/bin/env python3
"""Arrêter avec un contact : Serge ne lui écrit plus, ne lui répond plus.

Une conversation qui ne mène nulle part (un robot qui répond à chaque
message, un accusé de réception automatique, une liste de diffusion, une
conversation qui tourne en rond) ne doit jamais faire écrire Serge sans
fin (décision Q93, lot 10 bis). La fiche passe à ``STOPPED`` (« arrêté »),
une étape de la liste « Étapes où Serge ne répond plus du tout » de la
page Policy :

- ses envois en attente sont annulés ;
- ce qu'il écrit ensuite est rangé dans son fil sans être traité (la
  relève le marque ``ignored``) : il reste visible dans Mission Control.

Seule cette fiche est arrêtée, dans ce business : contrairement à une
désinscription, ses adresses ne sont pas bloquées. C'est une protection :
la capacité écrit elle-même, et note le changement au journal.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow

STOPPED = 'STOPPED'


def stop(conn: sqlite3.Connection, contact_id: str, reason: str) -> int:
    """Arrête la fiche ; rend le nombre d'envois annulés."""
    now = utcnow()
    cancelled = conn.execute(
        "UPDATE touches SET status='cancelled', last_error=?, updated_at=?"
        ' WHERE contact_id=?'
        " AND status IN ('to_write', 'pending', 'waiting_owner')",
        (f'contact arrêté : {reason}', now, contact_id),
    ).rowcount
    row = conn.execute(
        'SELECT venture_id FROM contacts WHERE id=?'
        " AND funnel_state NOT IN ('OPTED_OUT', ?)",
        (contact_id, STOPPED),
    ).fetchone()
    if row is not None:
        conn.execute(
            'UPDATE contacts SET funnel_state=?, updated_at=? WHERE id=?',
            (STOPPED, now, contact_id),
        )
        append_event(
            conn,
            actor='conversations',
            type='contact.stopped',
            venture_id=str(row[0]),
            payload={'reason': reason, 'cancelled': cancelled},
            rows=[('contacts', contact_id)],
        )
    return cancelled


def stop_contact(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Arrêter avec un contact » : ``{contact_id, reason}``."""
    contact = str(args.get('contact_id') or '')
    if not contact:
        return {'ok': False, 'code': 'contact_manquant'}
    reason = str(args.get('reason') or '').strip() or 'conversation sans issue'
    return {'ok': True, 'cancelled': stop(conn, contact, reason)}
