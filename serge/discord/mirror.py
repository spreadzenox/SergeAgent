#!/usr/bin/env python3
"""Miroir tickets → Discord (forum + urgent + digest, H §2).

DB = vérité : thread_ref JSON {post, message, état, items, date}.
Création si absent, édition si état/items changé, jamais de doublon.
Urgent : GUICHET + veto < 1h + ALERT (miroir toujours, mention selon
quiet hours — seul GUICHET TTL < 15 min sonne la nuit).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from serge.discord import render as renderer
from serge.discord.rest import (
    create_forum_post,
    edit_message,
    list_messages,
    send_message,
)

OPENISH = frozenset({'OPEN', 'DISCUSSING'})
PARIS = 'Europe/Paris'


def read_ref(thread_ref: str) -> dict[str, Any]:
    """Parse thread_ref ({} si absent/corrompu → re-miroir).

    Args:
        thread_ref: JSON stocké en DB.

    Returns:
        Dict (post_id, message_id, state, items, urgent...).
    """
    try:
        data = json.loads(thread_ref or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _view(ticket: Mapping[str, Any]) -> dict[str, Any]:
    view = dict(ticket)
    try:
        payload = json.loads(ticket.get('payload_json') or '{}')
    except (TypeError, ValueError):
        payload = {}
    view['payload'] = payload if isinstance(payload, dict) else {}
    return view


def _write_ref(
    connection: sqlite3.Connection, ticket_id: str, ref: dict[str, Any]
) -> None:
    connection.execute(
        'UPDATE tickets SET thread_ref=? WHERE id=?',
        (json.dumps(ref, ensure_ascii=False), ticket_id),
    )


def _minutes_left(expiry_at: str, now_iso: str) -> float:
    try:
        delta = datetime.fromisoformat(expiry_at) - datetime.fromisoformat(
            now_iso
        )
    except ValueError:
        return float('inf')
    return delta.total_seconds() / 60.0


def in_quiet_hours(policy: Mapping[str, Any], now_iso: str) -> bool:
    """Fenêtre silence owner (policy windows.quiet_hours, Paris).

    Args:
        policy: Policy (windows.quiet_hours [[23,0,8,0]]).
        now_iso: Maintenant ISO.

    Returns:
        True si notifications non urgentes interdites.
    """
    try:
        current = datetime.fromisoformat(now_iso).astimezone(ZoneInfo(PARIS))
    except ValueError:
        return False
    windows = (policy.get('windows') or {}).get('quiet_hours') or []
    moment = (current.hour, current.minute)
    for slot in windows:
        try:
            start_h, start_m, end_h, end_m = (int(item) for item in slot)
        except (TypeError, ValueError):
            continue
        if (start_h, start_m) <= (end_h, end_m):
            if (start_h, start_m) <= moment < (end_h, end_m):
                return True
        elif moment >= (start_h, start_m) or moment < (end_h, end_m):
            return True
    return False


def _needs_urgent(
    ticket: Mapping[str, Any], spec: Mapping[str, Any], now_iso: str
) -> bool:
    if str(ticket.get('state') or '') not in OPENISH:
        return False
    if spec.get('mirror_urgent'):
        return True
    if ticket.get('type') == 'VETO_AMONT':
        return _minutes_left(str(ticket.get('expiry_at') or ''), now_iso) < 60
    return False


def mirror_ticket(
    connection: sqlite3.Connection,
    token: str,
    discord_cfg: Mapping[str, str],
    ticket: Mapping[str, Any],
    spec: Mapping[str, Any],
    policy: Mapping[str, Any],
    *,
    h1: Mapping[str, Any] | None = None,
    now_iso: str = '',
) -> dict[str, Any]:
    """Synchronise un ticket (création/édition forum + urgent + digest).

    Args:
        connection: Connexion canon (commit par l'appelant).
        token: Token bot (header only).
        discord_cfg: Ids guild/forum/urgent/digest/owner.
        ticket: Vue get_ticket (payload_json brut accepté).
        spec: Déclaration registre du type.
        policy: Policy (quiet hours).
        h1: Rendu H1 (ou None = brut).
        now_iso: Maintenant ISO.

    Returns:
        Dict actions {forum: created|updated|fresh, urgent: bool...}.
    """
    view = _view(ticket)
    ticket_id = str(view.get('id') or '')
    ref = read_ref(str(view.get('thread_ref') or ''))
    card = renderer.render_card(view, spec, h1=h1, now_iso=now_iso)
    done: dict[str, Any] = {'forum': 'fresh', 'urgent': False, 'digest': False}
    if view.get('type') in {'FYI', 'REQUESTED'}:
        if not ref.get('message_id'):
            sent = send_message(
                token, str(discord_cfg.get('digest_channel_id') or ''), card
            )
            ref = {
                'channel': 'digest',
                'message_id': sent.get('id', ''),
                'state': view.get('state'),
                'at': now_iso,
            }
            _write_ref(connection, ticket_id, ref)
            done['digest'] = True
        return done
    if not ref.get('post_id'):
        post = create_forum_post(
            token,
            str(discord_cfg.get('forum_channel_id') or ''),
            str(view.get('title') or view.get('type'))[:100],
            card,
        )
        post_id = str(post.get('id') or '')
        message_id = ''
        try:
            first = list_messages(token, post_id, limit=1)
            if first:
                message_id = str(first[0].get('id') or '')
        except ValueError:
            message_id = ''
        ref = {
            'post_id': post_id,
            'message_id': message_id,
            'state': view.get('state'),
            'items': len(view.get('items') or []),
            'at': now_iso,
        }
        _write_ref(connection, ticket_id, ref)
        done['forum'] = 'created'
    elif ref.get('state') != view.get('state') or ref.get('items') != len(
        view.get('items') or []
    ):
        if ref.get('message_id'):
            edit_message(
                token, str(ref['post_id']), str(ref['message_id']), card
            )
        ref['state'] = view.get('state')
        ref['items'] = len(view.get('items') or [])
        ref['at'] = now_iso
        _write_ref(connection, ticket_id, ref)
        done['forum'] = 'updated'
    if _needs_urgent(view, spec, now_iso) and not ref.get('urgent_message_id'):
        ttl_left = _minutes_left(str(view.get('expiry_at') or ''), now_iso)
        loud = (not in_quiet_hours(policy, now_iso)) or (
            view.get('type') == 'GUICHET' and ttl_left < 15
        )
        mention = (
            f'<@{discord_cfg.get("owner_user_id")}>'
            if loud
            else '(silencieux)'
        )
        line = renderer.render_urgent_line(
            view, str(discord_cfg.get('owner_user_id') or ''), now_iso
        )
        if not loud:
            line = line.replace(
                f'<@{discord_cfg.get("owner_user_id")}>', '(silencieux)'
            )
        sent = send_message(
            token,
            str(discord_cfg.get('urgent_channel_id') or ''),
            {'content': line},
        )
        ref['urgent_message_id'] = sent.get('id', '')
        _write_ref(connection, ticket_id, ref)
        done['urgent'] = True
        done['mention'] = mention
    return done


def due_tickets(connection: sqlite3.Connection) -> list[str]:
    """Tickets à miroiriser (OPEN/DISCUSSING, absent ou état/items datés).

    Args:
        connection: Connexion canon (lecture).

    Returns:
        Ids par ancienneté (création ASC).
    """
    rows = connection.execute(
        'SELECT id, state, thread_ref FROM tickets WHERE state IN'
        " ('OPEN','DISCUSSING') ORDER BY created_at ASC"
    ).fetchall()
    due: list[str] = []
    for ticket_id, state, thread_ref in rows:
        ref = read_ref(str(thread_ref or ''))
        if not ref.get('post_id') and not ref.get('message_id'):
            due.append(str(ticket_id))
            continue
        if ref.get('state') != state:
            due.append(str(ticket_id))
            continue
        count = connection.execute(
            'SELECT COUNT(*) FROM ticket_items WHERE ticket_id=?',
            (ticket_id,),
        ).fetchone()
        if ref.get('items') != (int(count[0]) if count else 0):
            due.append(str(ticket_id))
    return due
