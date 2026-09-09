#!/usr/bin/env python3
"""Scheduler SQL-first: premier READY gagne. 0 LLM, jamais de débat."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow


def next_ready(
    connection: sqlite3.Connection, now: str | None = None
) -> dict[str, Any] | None:
    """Prochain travail READY (priorité, FIFO). None = idle légitime.

    Ne sert que les ventures schedulables (B5 : lifecycle découplé).
    Le scheduler ne sait pas ce qu'est un email ou une facture.

    Args:
        connection: Connexion canon.
        now: Horodatage ISO (défaut : maintenant UTC).

    Returns:
        Le work_item (dict) ou None si rien n'est READY.
    """
    moment = now or utcnow()
    row = connection.execute(
        'SELECT id, kind, venture_id, campaign_id, contact_id, ticket_id,'
        ' status, priority, payload_json, blocked_until, attempts,'
        ' idempotency_key, created_at, updated_at FROM work_items'
        " WHERE status='READY' AND (blocked_until='' OR blocked_until<=?)"
        ' AND venture_id IN (SELECT id FROM ventures WHERE schedulable=1)'
        ' ORDER BY priority DESC, created_at ASC LIMIT 1',
        (moment,),
    ).fetchone()
    return dict(row) if row else None


def enqueue(
    connection: sqlite3.Connection,
    *,
    kind: str,
    idempotency_key: str,
    venture_id: str = '',
    campaign_id: str = '',
    contact_id: str = '',
    ticket_id: str = '',
    priority: int = 0,
    payload: dict[str, Any] | None = None,
    blocked_until: str = '',
) -> str:
    """Crée un work_item READY (idempotent sur la clé).

    Args:
        connection: Connexion canon (commit par l'appelant).
        kind: Type de travail (ex. call.place, email.send).
        idempotency_key: Clé unique (rejeu = no-op prouvé).
        venture_id: Venture scope ('' = global).
        campaign_id: Campagne scope.
        contact_id: Contact scope.
        ticket_id: Ticket déclencheur éventuel.
        priority: Plus haut = servi en premier.
        payload: Données typées du travail (JSON).
        blocked_until: ISO UTC, '' = immédiatement READY.

    Returns:
        L'id du work_item (existant si clé déjà vue).
    """
    work_id = f'w_{abs(hash((kind, idempotency_key))) % 10**12:012d}'
    moment = utcnow()
    connection.execute(
        'INSERT INTO work_items(id, kind, venture_id, campaign_id,'
        ' contact_id, ticket_id, status, priority, payload_json,'
        ' blocked_until, attempts, idempotency_key, created_at, updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)'
        ' ON CONFLICT(idempotency_key) DO NOTHING',
        (
            work_id,
            kind,
            venture_id,
            campaign_id,
            contact_id,
            ticket_id,
            'READY',
            priority,
            json.dumps(payload or {}, ensure_ascii=False),
            blocked_until,
            0,
            idempotency_key,
            moment,
            moment,
        ),
    )
    row = connection.execute(
        'SELECT id FROM work_items WHERE idempotency_key=?',
        (idempotency_key,),
    ).fetchone()
    found = str(row[0]) if row else work_id
    append_event(
        connection,
        actor='scheduler',
        type='work.enqueued',
        venture_id=venture_id,
        payload={'id': found, 'kind': kind},
        links={'campaign': campaign_id, 'contact': contact_id},
    )
    return found


def claim(
    connection: sqlite3.Connection, work_id: str
) -> dict[str, Any] | None:
    """Passe un item READY en RUNNING (+1 attempt). Atomique.

    Args:
        connection: Connexion canon (commit par l'appelant).
        work_id: Id du work_item.

    Returns:
        L'item reclamé, ou None s'il n'était plus READY.
    """
    moment = utcnow()
    cursor = connection.execute(
        "UPDATE work_items SET status='RUNNING', attempts=attempts+1,"
        ' updated_at=? WHERE id=? AND status=?',
        (moment, work_id, 'READY'),
    )
    if not cursor.rowcount:
        return None
    append_event(
        connection,
        actor='scheduler',
        type='work.claimed',
        payload={'id': work_id},
    )
    row = connection.execute(
        'SELECT id, kind, venture_id, campaign_id, contact_id, ticket_id,'
        ' status, priority, payload_json, blocked_until, attempts,'
        ' idempotency_key, created_at, updated_at FROM work_items'
        ' WHERE id=?',
        (work_id,),
    ).fetchone()
    return dict(row) if row else None


def complete(
    connection: sqlite3.Connection, work_id: str, result: dict | None = None
) -> bool:
    """Marque un item RUNNING comme DONE (+ résultat optionnel).

    Args:
        connection: Connexion canon (commit par l'appelant).
        work_id: Id du work_item.
        result: RésultatJSON fusionné dans le payload (clés result_*).

    Returns:
        True si la transition a eu lieu.
    """
    row = connection.execute(
        'SELECT payload_json FROM work_items WHERE id=? AND status=?',
        (work_id, 'RUNNING'),
    ).fetchone()
    if not row:
        return False
    payload = json.loads(row[0] or '{}')
    if result:
        payload['result'] = result
    connection.execute(
        'UPDATE work_items SET status=?, payload_json=?, updated_at=?'
        ' WHERE id=?',
        ('DONE', json.dumps(payload, ensure_ascii=False), utcnow(), work_id),
    )
    append_event(
        connection,
        actor='scheduler',
        type='work.completed',
        payload={'id': work_id},
    )
    return True


def fail(
    connection: sqlite3.Connection,
    work_id: str,
    error: str,
    retry_at: str = '',
) -> bool:
    """Échec : FAILED définitif, ou READY replanifié si retry_at donné.

    Args:
        connection: Connexion canon (commit par l'appelant).
        work_id: Id du work_item RUNNING.
        error: Code d'erreur (jamais de prose parsée).
        retry_at: ISO UTC pour replanifier, '' = échec définitif.

    Returns:
        True si la transition a eu lieu.
    """
    status = 'READY' if retry_at else 'FAILED'
    cursor = connection.execute(
        'UPDATE work_items SET status=?, blocked_until=?, updated_at=?'
        ' WHERE id=? AND status=?',
        (status, retry_at, utcnow(), work_id, 'RUNNING'),
    )
    if not cursor.rowcount:
        return False
    append_event(
        connection,
        actor='scheduler',
        type='work.failed',
        payload={'id': work_id, 'error': error, 'retry_at': retry_at},
    )
    return True
