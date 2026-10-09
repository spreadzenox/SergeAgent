#!/usr/bin/env python3
"""Tickets : erreur, ids, événements, lecture brute (interne package)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import utcnow


class TicketError(ValueError):
    pass


def new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


def record_event(
    connection: sqlite3.Connection,
    ticket_id: str,
    actor: str,
    kind: str,
    payload: dict[str, Any] | None = None,
) -> None:
    connection.execute(
        'INSERT INTO ticket_events(ticket_id, ts, actor, kind, payload_json)'
        ' VALUES(?,?,?,?,?)',
        (
            ticket_id,
            utcnow(),
            actor,
            kind,
            json.dumps(payload or {}, ensure_ascii=False),
        ),
    )


def fetch_ticket(
    connection: sqlite3.Connection, ticket_id: str
) -> sqlite3.Row:
    """Le ticket, lisible par le nom de ses colonnes quelle que soit la
    connexion (une tâche peut ouvrir un ticket)."""
    cursor = connection.cursor()
    cursor.row_factory = sqlite3.Row
    row = cursor.execute(
        'SELECT id, type, title, state, payload_json, expiry_at,'
        ' default_action, versions_json, thread_ref, created_at, updated_at'
        ' FROM tickets WHERE id=?',
        (ticket_id,),
    ).fetchone()
    if not row:
        raise TicketError(f'ticket inconnu : {ticket_id}')
    return row


def already_applied(
    connection: sqlite3.Connection, ticket_id: str, decision_id: str
) -> bool:
    """Dédup double-clic (decision_id partagé Discord ↔ MC, ticket_events).

    Args:
        connection: Connexion canon (lecture).
        ticket_id: Ticket visé.
        decision_id: Id d'acte (interaction Discord ou mc-…).

    Returns:
        True si cet acte a déjà été appliqué.
    """
    row = connection.execute(
        'SELECT 1 FROM ticket_events WHERE ticket_id=?'
        " AND json_extract(payload_json,'$.decision_id')=?",
        (ticket_id, decision_id),
    ).fetchone()
    return row is not None


# Les champs d'une carte au plus (une conversation en a sept).
CHAMPS_MAX = 8


def champs_carte(
    ticket: Mapping[str, Any], spec: Mapping[str, Any]
) -> list[tuple[str, str]]:
    """Les champs d'une carte : ceux du type de ticket (``fields``), dans
    leur ordre, avec leur valeur dans le ticket.

    Args:
        ticket: Ticket (payload dict ou payload_json str).
        spec: Type du ticket en base (fields).

    Returns:
        Liste [(titre, texte)] (au plus ``CHAMPS_MAX``, vide = '—').
    """
    payload = ticket.get('payload')
    if payload is None and isinstance(ticket.get('payload_json'), str):
        try:
            payload = json.loads(str(ticket.get('payload_json')) or '{}')
        except ValueError:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    champs = []
    for key in list(spec.get('fields') or [])[:CHAMPS_MAX]:
        value = payload.get(key, '—')
        if isinstance(value, (dict, list)):
            value = f'{len(value)} élément(s)'
        champs.append((str(key), str(value)))
    return champs
