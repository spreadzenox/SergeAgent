#!/usr/bin/env python3
"""Transitions déterministes du funnel contact."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from serge.db.store import append_event, utcnow
from serge.funnels.contact_errors import TERMINAL, ContactError


def _get(conn: sqlite3.Connection, contact_id: str) -> sqlite3.Row:
    row = conn.execute(
        'SELECT id, venture_id, funnel_state, regime, last_inbound_at'
        ' FROM contacts WHERE id=?',
        (contact_id,),
    ).fetchone()
    if not row:
        raise ContactError(f'contact inconnu : {contact_id}')
    return row


def _move(
    conn: sqlite3.Connection,
    contact_id: str,
    allowed_from: frozenset[str],
    to_state: str,
    reason: str = '',
) -> None:
    row = _get(conn, contact_id)
    if row['funnel_state'] not in allowed_from:
        raise ContactError(
            f'{contact_id} : {row["funnel_state"]} → {to_state} interdit'
        )
    conn.execute(
        'UPDATE contacts SET funnel_state=?, updated_at=? WHERE id=?',
        (to_state, utcnow(), contact_id),
    )
    append_event(
        conn,
        actor='contacts',
        type=f'contact.{to_state.lower()}',
        venture_id=row['venture_id'],
        payload={
            'id': contact_id,
            'from': row['funnel_state'],
            'reason': reason,
        },
        links={'contact': contact_id},
    )


def qualify(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'NEW'}), 'QUALIFIED')


def reject(conn: sqlite3.Connection, contact_id: str, reason: str) -> None:
    _move(
        conn, contact_id, frozenset({'NEW', 'QUALIFIED'}), 'REJECTED', reason
    )


def start_contacting(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'QUALIFIED'}), 'CONTACTING')


def mark_engaged(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'CONTACTING'}), 'ENGAGED')


def mark_intent(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'CONTACTING', 'ENGAGED'}), 'INTENT')


def to_meeting(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'INTENT'}), 'MEETING')


def to_customer(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(conn, contact_id, frozenset({'INTENT', 'MEETING'}), 'CUSTOMER')


def mark_unreachable(conn: sqlite3.Connection, contact_id: str) -> None:
    _move(
        conn, contact_id, frozenset({'CONTACTING', 'ENGAGED'}), 'UNREACHABLE'
    )


def opt_out(conn: sqlite3.Connection, contact_id: str) -> None:
    row = _get(conn, contact_id)
    if row['funnel_state'] in TERMINAL:
        raise ContactError(f'{contact_id} : déjà terminal')
    _move(
        conn,
        contact_id,
        frozenset(
            {
                'NEW',
                'QUALIFIED',
                'CONTACTING',
                'ENGAGED',
                'INTENT',
                'MEETING',
            }
        ),
        'OPTED_OUT',
    )


def mark_blocked(
    conn: sqlite3.Connection, contact_id: str, reason: str
) -> None:
    row = _get(conn, contact_id)
    if row['funnel_state'] in TERMINAL:
        raise ContactError(f'{contact_id} : déjà terminal')
    _move(
        conn,
        contact_id,
        frozenset(
            {
                'NEW',
                'QUALIFIED',
                'CONTACTING',
                'ENGAGED',
                'INTENT',
                'MEETING',
            }
        ),
        'BLOCKED',
        reason,
    )


def mark_invalid(
    conn: sqlite3.Connection, contact_id: str, reason: str
) -> None:
    row = _get(conn, contact_id)
    if row['funnel_state'] in TERMINAL:
        raise ContactError(f'{contact_id} : déjà terminal')
    _move(
        conn,
        contact_id,
        frozenset(
            {
                'NEW',
                'QUALIFIED',
                'CONTACTING',
                'ENGAGED',
                'INTENT',
                'MEETING',
            }
        ),
        'INVALID',
        reason,
    )


def note_inbound(
    conn: sqlite3.Connection, contact_id: str, now: str | None = None
) -> str:
    """Signale entrant : passe en INBOUND (+ horodate). Idempotent."""
    row = _get(conn, contact_id)
    moment = now or utcnow()
    conn.execute(
        'UPDATE contacts SET regime=?, last_inbound_at=?, updated_at=?'
        ' WHERE id=?',
        ('INBOUND', moment, moment, contact_id),
    )
    if row['regime'] != 'INBOUND':
        append_event(
            conn,
            actor='contacts',
            type='contact.inbound',
            venture_id=row['venture_id'],
            links={'contact': contact_id},
        )
    return 'INBOUND'


def refresh_regime(
    conn: sqlite3.Connection,
    contact_id: str,
    silence_days: int,
    now: str | None = None,
) -> str:
    """Retour OUTBOUND après silence, sinon conserve INBOUND."""
    row = _get(conn, contact_id)
    if row['regime'] != 'INBOUND' or not row['last_inbound_at']:
        return str(row['regime'])
    moment = now or utcnow()
    last = datetime.fromisoformat(row['last_inbound_at'])
    if datetime.fromisoformat(moment) - last > timedelta(days=silence_days):
        conn.execute(
            'UPDATE contacts SET regime=?, updated_at=? WHERE id=?',
            ('OUTBOUND', moment, contact_id),
        )
        append_event(
            conn,
            actor='contacts',
            type='contact.outbound',
            venture_id=row['venture_id'],
            payload={'silence_days': silence_days},
            links={'contact': contact_id},
        )
        return 'OUTBOUND'
    return 'INBOUND'
