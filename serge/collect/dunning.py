#!/usr/bin/env python3
"""Relances bornées (B §5) : OVERDUE → J+7 polie → J+14 ferme → STOP+ticket.

Calcule les dus, enregistre les envois. L'envoi (template pur) est au
mailer ; le ticket STOP au caller. 2 max, opt-out respecté ailleurs
(guards). Jours calendaires, seuils en policy (collect.dunning_days).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from serge.db.store import append_event, utcnow


def _envelope(row: sqlite3.Row) -> dict[str, Any]:
    data = json.loads(row['receipt_json'] or '{}')
    return data if isinstance(data, dict) else {}


def _reminders_sent(envelope: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = envelope.get('reminders') or []
    return [item for item in items if isinstance(item, dict)]


def due_reminders(
    conn: sqlite3.Connection,
    venture_id: str,
    policy: Mapping[str, Any],
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Relances dues : [{tx_id, level, action}] (remind | ticket_stop).

    Args:
        conn: Connexion canon (lecture).
        venture_id: Venture scope.
        policy: Policy (collect.dunning_days [7, 14]).
        now: ISO UTC (défaut : maintenant).

    Returns:
        Dus triés (ancien d'abord). Vide = rien à faire.
    """
    moment = now or utcnow()
    current = datetime.fromisoformat(moment)
    days = list((policy.get('collect') or {}).get('dunning_days', [7, 14]))
    rows = conn.execute(
        'SELECT id, updated_at, receipt_json FROM transactions'
        " WHERE venture_id=? AND status='overdue' ORDER BY updated_at ASC",
        (venture_id,),
    ).fetchall()
    due: list[dict[str, Any]] = []
    for row in rows:
        overdue_since = datetime.fromisoformat(row['updated_at'])
        age_days = (current - overdue_since).days
        sent = _reminders_sent(_envelope(row))
        level = len(sent)
        if level >= len(days):
            due.append(
                {'tx_id': row['id'], 'level': level, 'action': 'ticket_stop'}
            )
        elif age_days >= int(days[level]):
            due.append(
                {'tx_id': row['id'], 'level': level, 'action': 'remind'}
            )
    return due


def record_reminder(
    conn: sqlite3.Connection, tx_id: str, level: int, now: str | None = None
) -> None:
    """Enregistre une relance envoyée (niveau + date, événement).

    Args:
        conn: Connexion canon (commit par l'appelant).
        tx_id: Transaction relancée.
        level: Niveau envoyé (0 = polie, 1 = ferme).
        now: ISO UTC (défaut : maintenant).
    """
    row = conn.execute(
        'SELECT receipt_json, venture_id FROM transactions WHERE id=?',
        (tx_id,),
    ).fetchone()
    if not row:
        raise ValueError(f'transaction inconnue : {tx_id}')
    envelope = json.loads(row[0] or '{}')
    if not isinstance(envelope, dict):
        envelope = {}
    reminders = _reminders_sent(envelope)
    reminders.append({'level': level, 'at': now or utcnow()})
    envelope['reminders'] = reminders
    conn.execute(
        'UPDATE transactions SET receipt_json=? WHERE id=?',
        (json.dumps(envelope, ensure_ascii=False), tx_id),
    )
    append_event(
        conn,
        actor='collect',
        type='collect.reminder',
        venture_id=row[1],
        payload={'id': tx_id, 'level': level},
        links={'transaction': tx_id},
    )
