#!/usr/bin/env python3
"""Les tickets en message privé, chez chaque administrateur (Q85, Q86).

La base est la vérité ; le bot la recopie à chaque tour :

- un ticket ouvert part en message privé à chaque administrateur ajouté
  avant lui (les tickets plus anciens restent dans Mission Control), avec
  notification, à toute heure ;
- dès qu'il change d'état (tranché sur Discord ou dans Mission Control,
  expiré, annulé), sa carte est mise à jour chez tous : boutons morts, et
  qui l'a tranché.

Un message qui ne part pas (la personne n'est pas sur le serveur, ou
refuse les messages privés) est réessayé après ``RETRY_MINUTES``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.discord.render import render_card
from serge.discord.rest import (
    DiscordError,
    create_dm,
    edit_message,
    send_message,
)
from serge.tickets import get_ticket
from serge.tickets.admins import admin_name, admins
from serge.tickets.types import ticket_types

RETRY_MINUTES = 10
# L'état d'un message qui n'est pas parti.
ECHEC = 'ECHEC'
VERDICTS = {
    'APPROVED': 'Approuvé',
    'REJECTED': 'Rejeté',
    'EDITED': 'Modifié',
    'EXECUTED': 'Fait',
    'CLOSED': 'Fait',
    'EXPIRED': 'Expiré',
    'CANCELLED': 'Annulé',
}


def _tranche(conn: sqlite3.Connection, ticket: Mapping[str, Any]) -> str:
    """Qui a tranché le ticket, et comment ; ``''`` s'il est encore ouvert.

    Exemple : « Approuvé par Clem », « Rejeté dans Mission Control »,
    « Expiré : La policy actuelle reste. ».
    """
    state = str(ticket.get('state') or '')
    verdict = VERDICTS.get(state)
    if verdict is None:
        return ''
    if state == 'EXPIRED':
        detail = str(ticket.get('default_detail') or '')
        return f'{verdict} : {detail}' if detail else verdict
    row = conn.execute(
        'SELECT actor, payload_json FROM ticket_events WHERE ticket_id=?'
        ' AND kind=? ORDER BY id DESC LIMIT 1',
        (ticket['id'], f'transition.{state.lower()}'),
    ).fetchone()
    actor = str(row[0]) if row else ''
    note = ''
    if row:
        try:
            note = str(json.loads(row[1] or '{}').get('note') or '')
        except ValueError:
            note = ''
    if actor.startswith('discord:'):
        who = f' par {admin_name(conn, actor.split(":", 1)[1]) or "un administrateur"}'
    elif actor == 'owner':
        who = ' dans Mission Control'
    else:
        who = ''
    return f'{verdict}{who}' + (f' : {note}' if note else '')


def _carte(
    conn: sqlite3.Connection, ticket_id: str, now_iso: str
) -> dict[str, Any] | None:
    try:
        ticket = get_ticket(conn, ticket_id)
    except ValueError:
        return None
    spec = ticket_types(conn).get(str(ticket.get('type')))
    if not isinstance(spec, dict):
        return None
    try:
        payload = json.loads(ticket.get('payload_json') or '{}')
    except (TypeError, ValueError):
        payload = {}
    ticket = {
        **ticket,
        'payload': payload if isinstance(payload, dict) else {},
        'default_detail': spec.get('default_detail', ''),
    }
    ticket['tranche'] = _tranche(conn, ticket)
    return render_card(ticket, spec, now_iso=now_iso)


def _a_envoyer(
    conn: sqlite3.Connection, now_iso: str
) -> list[tuple[str, str, str]]:
    """Les (ticket, administrateur, état) qui n'ont pas encore leur message."""
    retry = (
        datetime.fromisoformat(now_iso) - timedelta(minutes=RETRY_MINUTES)
    ).isoformat()
    out = []
    for admin in admins(conn):
        for ticket_id, state in conn.execute(
            'SELECT t.id, t.state FROM tickets t'
            " WHERE t.state IN ('OPEN','DISCUSSING') AND t.created_at>=?"
            ' AND NOT EXISTS (SELECT 1 FROM ticket_messages m'
            ' WHERE m.ticket_id=t.id AND m.user_id=?'
            ' AND (m.shown_state<>? OR m.updated_at>?))'
            ' ORDER BY t.created_at',
            (admin['added_at'], admin['user_id'], ECHEC, retry),
        ).fetchall():
            out.append((str(ticket_id), admin['user_id'], str(state)))
    return out


def deliver(
    conn: sqlite3.Connection, token: str, now_iso: str | None = None
) -> int:
    """Envoie les tickets ouverts aux administrateurs qui ne les ont pas,
    et met à jour les cartes des tickets qui ont changé. Rend le nombre de
    messages envoyés ou modifiés."""
    moment = now_iso or utcnow()
    count = 0
    for ticket_id, user_id, state in _a_envoyer(conn, moment):
        carte = _carte(conn, ticket_id, moment)
        if carte is None:
            continue
        try:
            channel = create_dm(token, user_id)
            message = send_message(token, channel, carte)
            values = (channel, str(message.get('id') or ''), state)
        except DiscordError:
            values = ('', '', ECHEC)
        conn.execute(
            'INSERT OR REPLACE INTO ticket_messages(ticket_id, user_id,'
            ' channel_id, message_id, shown_state, updated_at)'
            ' VALUES(?,?,?,?,?,?)',
            (ticket_id, user_id, *values, moment),
        )
        conn.commit()
        count += values[2] != ECHEC
    # Une carte qui n'a pas pu être modifiée (message supprimé, réseau)
    # est réessayée après RETRY_MINUTES, ou dès que le ticket change.
    retry = (
        datetime.fromisoformat(moment) - timedelta(minutes=RETRY_MINUTES)
    ).isoformat()
    for ticket_id, user_id, channel, message_id in conn.execute(
        'SELECT m.ticket_id, m.user_id, m.channel_id, m.message_id'
        ' FROM ticket_messages m JOIN tickets t ON t.id=m.ticket_id'
        " WHERE m.message_id<>'' AND m.shown_state<>t.state"
        ' AND (t.updated_at>m.updated_at OR m.updated_at<=?)',
        (retry,),
    ).fetchall():
        carte = _carte(conn, str(ticket_id), moment)
        if carte is None:
            continue
        try:
            edit_message(token, str(channel), str(message_id), carte)
            shown = '(SELECT state FROM tickets WHERE id=?)'
        except DiscordError:
            shown = 'shown_state'
        conn.execute(
            f'UPDATE ticket_messages SET shown_state={shown}, updated_at=?'
            ' WHERE ticket_id=? AND user_id=?',
            (
                *((ticket_id,) if shown != 'shown_state' else ()),
                moment,
                ticket_id,
                user_id,
            ),
        )
        conn.commit()
        count += shown != 'shown_state'
    return count
