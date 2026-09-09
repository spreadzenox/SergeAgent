#!/usr/bin/env python3
"""Lifecycle tickets : générique, expiry + défaut (types en YAML, P1)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.tickets.shared import (
    TicketError,
    fetch_ticket,
    new_id,
    record_event,
)

DECIDED = frozenset({'APPROVED', 'REJECTED', 'EDITED'})
OPENISH = frozenset({'DRAFT', 'OPEN', 'DISCUSSING'})


def _transition(
    connection: sqlite3.Connection,
    ticket_id: str,
    allowed_from: frozenset[str],
    to_state: str,
    actor: str,
    extra: dict[str, Any] | None = None,
) -> None:
    row = fetch_ticket(connection, ticket_id)
    if row['state'] not in allowed_from:
        raise TicketError(
            f'{ticket_id} : {row["state"]} → {to_state} interdit'
        )
    connection.execute(
        'UPDATE tickets SET state=?, updated_at=? WHERE id=?',
        (to_state, utcnow(), ticket_id),
    )
    record_event(
        connection,
        ticket_id,
        actor,
        f'transition.{to_state.lower()}',
        {'from': row['state'], **(extra or {})},
    )


def _default_expiry(
    spec: Mapping[str, Any], now: datetime, ttl_minutes: int | None
) -> str:
    if ttl_minutes is not None:
        return (now + timedelta(minutes=ttl_minutes)).isoformat()
    hours = spec.get('expiry_hours')
    if hours is not None:
        return (now + timedelta(hours=float(hours))).isoformat()
    minutes = spec.get('expiry_minutes')
    if isinstance(minutes, list):
        minutes = minutes[0] if minutes else None
    if minutes is not None:
        return (now + timedelta(minutes=float(minutes))).isoformat()
    return ''


def create_ticket(
    connection: sqlite3.Connection,
    types: Mapping[str, Any],
    ticket_type: str,
    title: str,
    payload: dict[str, Any] | None = None,
    creator: str = 'serge',
    ttl_minutes: int | None = None,
    now: str | None = None,
) -> str:
    """Crée un ticket DRAFT (expiry + défaut issus du registre).

    Raises:
        TicketError: Type inconnu.
    """
    spec = types.get(ticket_type)
    if not isinstance(spec, Mapping):
        raise TicketError(f'type de ticket inconnu : {ticket_type}')
    moment = now or utcnow()
    current = datetime.fromisoformat(moment)
    ticket_id = new_id('t')
    connection.execute(
        'INSERT INTO tickets(id, type, title, state, payload_json, expiry_at,'
        ' default_action, versions_json, thread_ref, created_at, updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (
            ticket_id,
            ticket_type,
            title,
            'DRAFT',
            json.dumps(payload or {}, ensure_ascii=False),
            _default_expiry(spec, current, ttl_minutes),
            str(spec.get('default') or ''),
            '[]',
            '',
            moment,
            moment,
        ),
    )
    record_event(
        connection,
        ticket_id,
        creator,
        'transition.draft',
        {'type': ticket_type},
    )
    return ticket_id


def publish(connection: sqlite3.Connection, ticket_id: str) -> None:
    _transition(connection, ticket_id, frozenset({'DRAFT'}), 'OPEN', 'serge')


def discuss(connection: sqlite3.Connection, ticket_id: str) -> None:
    _transition(
        connection, ticket_id, frozenset({'OPEN'}), 'DISCUSSING', 'owner'
    )


def reopen(connection: sqlite3.Connection, ticket_id: str) -> None:
    _transition(
        connection, ticket_id, frozenset({'DISCUSSING'}), 'OPEN', 'owner'
    )


def decide(
    connection: sqlite3.Connection,
    ticket_id: str,
    outcome: str,
    actor: str = 'owner',
    note: str = '',
) -> None:
    """Décide : APPROVED | REJECTED | EDITED (depuis OPEN/DISCUSSING)."""
    if outcome not in DECIDED:
        raise TicketError(f'décision invalide : {outcome}')
    _transition(
        connection,
        ticket_id,
        frozenset({'OPEN', 'DISCUSSING'}),
        outcome,
        actor,
        {'note': note} if note else None,
    )
    if outcome == 'EDITED':
        row = fetch_ticket(connection, ticket_id)
        versions = json.loads(row['versions_json'] or '[]')
        versions.append({'n': len(versions) + 1, 'note': note, 'at': utcnow()})
        connection.execute(
            'UPDATE tickets SET versions_json=? WHERE id=?',
            (json.dumps(versions, ensure_ascii=False), ticket_id),
        )


def execute(
    connection: sqlite3.Connection,
    ticket_id: str,
    result: dict[str, Any] | None = None,
) -> None:
    _transition(connection, ticket_id, DECIDED, 'EXECUTED', 'serge', result)


def close(connection: sqlite3.Connection, ticket_id: str) -> None:
    _transition(
        connection, ticket_id, frozenset({'EXECUTED'}), 'CLOSED', 'serge'
    )


def cancel(
    connection: sqlite3.Connection, ticket_id: str, reason: str = ''
) -> None:
    _transition(
        connection,
        ticket_id,
        OPENISH,
        'CANCELLED',
        'serge',
        {'reason': reason} if reason else None,
    )


def expire_due(
    connection: sqlite3.Connection, now: str | None = None
) -> list[str]:
    """Expire les tickets dépassés : défaut annoncé appliqué + log.

    Returns:
        Ids expirés (tickets sans expiry ignorés).
    """
    moment = now or utcnow()
    rows = connection.execute(
        'SELECT id, state, default_action FROM tickets WHERE state IN'
        " ('DRAFT','OPEN','DISCUSSING') AND expiry_at<>'' AND expiry_at<=?",
        (moment,),
    ).fetchall()
    expired: list[str] = []
    for row in rows:
        connection.execute(
            'UPDATE tickets SET state=?, updated_at=? WHERE id=?',
            ('EXPIRED', moment, row[0]),
        )
        record_event(
            connection,
            row[0],
            'serge',
            'transition.expired',
            {'from': row[1], 'default_applied': row[2]},
        )
        expired.append(row[0])
    return expired
