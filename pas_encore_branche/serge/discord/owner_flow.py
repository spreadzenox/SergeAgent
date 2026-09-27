#!/usr/bin/env python3
"""Flux owner (H §6) : mention → H2/H3 → plan → ticket/ack.

H2/H3/sender injectables (tests sans LLM ni réseau). Bypass logué +
FYI post-hoc. Constitution refusée avant tout LLM (déjà dans le plan).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

from serge.discord.owner_in import parse_mention, plan_owner_message
from serge.discord.rest import send_message
from serge.points.interact import classify_owner_intent, judge_consequence
from serge.tickets import create_ticket, decide, publish


def thread_ticket(connection: sqlite3.Connection, channel_id: str) -> str:
    """Ticket dont le fil est ce canal ('' si aucun).

    Args:
        connection: Connexion canon (lecture).
        channel_id: Canal/thread Discord.

    Returns:
        L'id ticket ou ''.
    """
    if not channel_id:
        return ''
    row = connection.execute(
        'SELECT id FROM tickets WHERE thread_ref LIKE ?',
        (f'%{channel_id}%',),
    ).fetchone()
    return str(row[0]) if row else ''


def handle_owner_message(
    connection: sqlite3.Connection,
    policy: Mapping[str, Any],
    types: Mapping[str, Any],
    token: str,
    owner_user_id: str,
    bot_user_id: str,
    message: Mapping[str, Any],
    *,
    h2_fn: Callable[..., dict[str, Any]] = classify_owner_intent,
    h3_fn: Callable[..., dict[str, Any]] = judge_consequence,
    sender: Callable[..., dict[str, Any]] = send_message,
) -> dict[str, Any]:
    """Traite un message : filtres → plan → ticket/ack.

    Args:
        connection: Connexion canon (commit par l'appelant).
        policy: Policy (points H2/H3).
        types: Registre ticket-types.
        token: Token bot.
        owner_user_id: Snowflake owner (seul servi).
        bot_user_id: Snowflake bot (mentions).
        message: Objet MESSAGE_CREATE.
        h2_fn: Point H2 (défaut réel).
        h3_fn: Point H3 (défaut réel).
        sender: Envoi (défaut REST).

    Returns:
        Dict {handled, action?, ticket_id?}.
    """
    author = message.get('author') or {}
    if bool(author.get('bot')):
        return {'handled': False}
    if str(author.get('id') or '') != owner_user_id:
        return {'handled': False}
    text = parse_mention(str(message.get('content') or ''), bot_user_id)
    if text is None:
        return {'handled': False}
    channel_id = str(message.get('channel_id') or '')
    thread_ticket_id = thread_ticket(connection, channel_id)
    h2 = h2_fn(connection, policy, text)
    h3 = h3_fn(connection, policy, text)
    plan = plan_owner_message(
        text, thread_ticket_id=thread_ticket_id, h2=h2, h3=h3
    )
    action = str(plan.get('action') or '')
    if action in {'refuse', 'hint_buttons'}:
        sender(token, channel_id, {'content': str(plan.get('message') or '')})
        return {'handled': True, 'action': action}
    ticket_id = create_ticket(
        connection,
        types,
        'OWNER_ORDER',
        f'Ordre owner : {plan.get("intent")}',
        {
            'ordre': plan.get('body'),
            'discussion_serge': '',
            'consequences': plan.get('h3_criteres'),
            'intent': plan.get('intent'),
            'cible': plan.get('cible'),
            'bypass': plan.get('bypass'),
            'fil_origine': thread_ticket_id,
        },
        creator='owner',
    )
    if not plan.get('needs_confirm'):
        try:
            publish(connection, ticket_id)
            decide(
                connection,
                ticket_id,
                'APPROVED',
                actor='owner',
                note='direct (pas de conséquence)',
            )
        except ValueError:
            pass
    else:
        publish(connection, ticket_id)
    if plan.get('fyi_posthoc'):
        fyi = create_ticket(
            connection,
            types,
            'FYI',
            'Bypass owner utilisé',
            {'contenu': f'Ordre bypassé : {plan.get("body")}'},
        )
        publish(connection, fyi)
    sender(
        token,
        channel_id,
        {'content': f'Noté → ticket `{plan.get("intent")}` ouvert. 👆'},
    )
    return {'handled': True, 'action': action, 'ticket_id': ticket_id}
