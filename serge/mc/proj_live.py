#!/usr/bin/env python3
"""Projecteurs P0 Live : hero, urgents, file, feed, jauges (purs, testés)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.llm.runtime import daily_tokens
from serge.mc.proj_outils import apres_iso
from serge.scheduler import next_ready
from serge.tickets.lifecycle import OPENISH


def project_hero(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Ce qui se passe : RUNNING actuel + file READY (P0 hero).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {running: {id, kind, venture_id, since} | None, ready: int}.
    """
    _ = (policy, now)
    row = conn.execute(
        'SELECT id, kind, venture_id, created_at FROM work_items'
        " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    running = None
    if row is not None:
        running = {
            'id': row[0],
            'kind': row[1],
            'venture_id': row[2],
            'since': row[3],
        }
    ready = conn.execute(
        "SELECT COUNT(*) FROM work_items WHERE status='READY'"
    ).fetchone()[0]
    return {'running': running, 'ready': int(ready)}


def project_urgents(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Tickets urgents : GUICHET <15min, veto <1h, ALERT (P0 urgents).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, type, titre, expiry_at}]} (cap 20, expiries first).
    """
    _ = policy
    soon_15 = apres_iso(now, minutes=15)
    soon_60 = apres_iso(now, minutes=60)
    placeholders = ','.join('?' * len(OPENISH))
    rows = conn.execute(
        'SELECT id, type, title, expiry_at FROM tickets WHERE state IN'
        f' ({placeholders}) AND ((type=? AND expiry_at<>? AND expiry_at<?)'
        " OR (type=? AND expiry_at<>? AND expiry_at<?) OR type='ALERT')"
        " ORDER BY CASE WHEN expiry_at='' THEN 1 ELSE 0 END, expiry_at"
        ' LIMIT 20',
        (
            *sorted(OPENISH),
            'GUICHET',
            '',
            soon_15,
            'VETO_AMONT',
            '',
            soon_60,
        ),
    ).fetchall()
    return {
        'items': [
            {
                'id': row[0],
                'type': row[1],
                'titre': row[2],
                'expiry_at': row[3],
            }
            for row in rows
        ]
    }


def project_file(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """File d'exécution : RUNNING + READY + prochain (P0 file).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {running: [...cap 10], ready_count: int, next: {...} | None}.
    """
    _ = policy
    running = [
        {
            'id': row[0],
            'kind': row[1],
            'venture_id': row[2],
            'since': row[3],
        }
        for row in conn.execute(
            'SELECT id, kind, venture_id, created_at FROM work_items'
            " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    ]
    ready_count = conn.execute(
        "SELECT COUNT(*) FROM work_items WHERE status='READY'"
    ).fetchone()[0]
    nxt = next_ready(conn, now)
    following = None
    if nxt is not None:
        following = {
            'id': nxt['id'],
            'kind': nxt['kind'],
            'venture_id': nxt['venture_id'],
        }
    return {
        'running': running,
        'ready_count': int(ready_count),
        'next': following,
    }


def _feed_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT ts, type, actor, payload_json FROM events'
        ' ORDER BY id DESC LIMIT 30'
    ).fetchall():
        try:
            extra = json.loads(row[3] or '{}')
        except ValueError:
            extra = {}
        items.append(
            {
                'ts': row[0],
                'source': 'event',
                'kind': row[1],
                'titre': '',
                'extra': extra if isinstance(extra, dict) else {},
            }
        )
    return items


def _feed_tickets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT te.ts, te.kind, te.actor, t.id, t.title'
        ' FROM ticket_events te LEFT JOIN tickets t'
        ' ON t.id=te.ticket_id ORDER BY te.id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[0],
                'source': 'ticket',
                'kind': row[1],
                'titre': str(row[4] or ''),
                'extra': {'ticket_id': row[3], 'actor': row[2]},
            }
        )
    return items


def _feed_touches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT t.created_at, t.channel, t.kind, t.status,'
        ' COALESCE(c.display, c.email, t.contact_id)'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' ORDER BY t.created_at DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[0],
                'source': 'touche',
                'kind': f'{row[1]}.{row[3]}',
                'titre': str(row[4] or ''),
                'extra': {'contact_kind': row[2]},
            }
        )
    return items


def project_feed(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Feed unifié : events + tickets + touches, triés (P0 feed).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{ts, source, kind, titre, extra}] cap 30}.
        Calls voix : différés au lot 7 (ledger séparé).
    """
    _ = (policy, now)
    items = _feed_events(conn) + _feed_tickets(conn) + _feed_touches(conn)
    items.sort(key=lambda item: str(item['ts']), reverse=True)
    return {'items': items[:30]}


def project_jauges(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Budgets du jour : LLM (tokens + estimation garde) + email (P0).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (budget + quotas).
        now: Maintenant ISO UTC.

    Returns:
        Dict {llm: {...}, email: {...}} (ratios ou None si incalculable).
        Coûts fins au lot 9 (tarifs) ; voix au lot 7 (CDR séparé).
    """
    day = now[:10]
    spent_in, spent_out = daily_tokens(conn, day)
    tokens = spent_in + spent_out
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    rate = float(budget.get('llm_eur_per_1k_tokens', 0) or 0)
    eur = tokens / 1000 * rate
    sent = conn.execute(
        "SELECT COUNT(*) FROM touches WHERE channel='email'"
        " AND status='sent' AND created_at LIKE ?",
        (f'{day}%',),
    ).fetchone()[0]
    quotas = policy.get('quotas') or {}
    email_cap = quotas.get('email_per_mailbox_per_day', 0)
    try:
        email_cap = int(email_cap)
    except (TypeError, ValueError):
        email_cap = 0
    return {
        'llm': {
            'tokens_jour': tokens,
            'eur_estimes': round(eur, 4),
            'plafond_eur': cap,
            'ratio': (eur / cap) if cap > 0 else None,
        },
        'email': {
            'envoyes': int(sent),
            'quota': email_cap,
            'ratio': (int(sent) / email_cap) if email_cap > 0 else None,
        },
    }
