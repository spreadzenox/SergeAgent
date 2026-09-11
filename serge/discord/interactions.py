#!/usr/bin/env python3
"""Interactions Discord → actes tickets (H §1.2 : boutons = actes typés).

parse custom_id `t:<ticket>:<action>[:<item>]` → garde owner → dédup
decision_id (interaction id, ticket_events) → transition lifecycle.
LLM jamais sur le chemin de décision. Refus = message éphémère FR.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.tickets.items import set_item, tout_approuver
from serge.tickets.lifecycle import decide, discuss
from serge.tickets.shared import TicketError, already_applied, record_event

APPROVE = frozenset(
    {
        'approuver',
        'approuver_version',
        'cest_fait',
        'confirmer',
        'ouvrir',
        'tout_approuver',
    }
)
REJECT = frozenset({'rejeter', 'abandonner', 'refuser', 'annuler'})
ITEM_STATES = {'garder': 'keep', 'modifier': 'edit', 'jeter': 'drop'}


def parse_custom_id(custom_id: str) -> tuple[str, str, str] | None:
    """Parse `t:<ticket>:<action>[:<item>]` (None si malformé).

    Args:
        custom_id: custom_id du composant Discord.

    Returns:
        Tuple (ticket_id, action, item_id?) ou None.
    """
    parts = (custom_id or '').split(':')
    if len(parts) not in {3, 4} or parts[0] != 't':
        return None
    ticket_id, action = parts[1], parts[2]
    if not ticket_id or not action:
        return None
    return (ticket_id, action, parts[3] if len(parts) == 4 else '')


def actor_id(interaction: Mapping[str, Any]) -> str:
    """Snowflake auteur (member.user.id ou user.id, '' si absent).

    Args:
        interaction: Objet interaction Discord.

    Returns:
        L'id auteur.
    """
    member = interaction.get('member') or {}
    user = member.get('user') or interaction.get('user') or {}
    return str(user.get('id') or '')


def _stamp(
    connection: sqlite3.Connection,
    ticket_id: str,
    action: str,
    decision_id: str,
    extra: dict[str, Any] | None = None,
) -> None:
    record_event(
        connection,
        ticket_id,
        'owner',
        f'discord.{action}',
        {'decision_id': decision_id, **(extra or {})},
    )


def route_interaction(
    connection: sqlite3.Connection,
    interaction: Mapping[str, Any],
    owner_user_id: str,
) -> dict[str, Any]:
    """Route une interaction composant vers un acte ticket.

    Args:
        connection: Connexion canon (commit par l'appelant).
        interaction: Objet Discord (id, token, member/user, data).
        owner_user_id: Snowflake owner (canaux owner-only).

    Returns:
        Dict status applied|duplicate|refused|error (+ ticket/action/msg).
    """
    data = interaction.get('data') or {}
    parsed = parse_custom_id(str(data.get('custom_id') or ''))
    if parsed is None:
        return {'status': 'error', 'error': 'custom_id_malforme'}
    ticket_id, action, item_id = parsed
    if not owner_user_id or actor_id(interaction) != owner_user_id:
        return {
            'status': 'refused',
            'error': 'owner_only',
            'message': 'Réservé au propriétaire.',
        }
    decision_id = str(interaction.get('id') or '')
    if decision_id and already_applied(connection, ticket_id, decision_id):
        return {'status': 'duplicate', 'ticket_id': ticket_id}
    try:
        if action in APPROVE:
            if action == 'tout_approuver':
                tout_approuver(connection, ticket_id)
            decide(connection, ticket_id, 'APPROVED')
        elif action in REJECT:
            decide(connection, ticket_id, 'REJECTED')
        elif action == 'editer':
            decide(connection, ticket_id, 'EDITED', note='via Discord')
        elif action in {'discuter', 'discuter_fil'}:
            discuss(connection, ticket_id)
        elif action in ITEM_STATES:
            if not item_id:
                return {'status': 'error', 'error': 'item_manquant'}
            set_item(connection, item_id, ITEM_STATES[action])
        elif action == 'accuse_reception':
            pass
        elif action == 'reponse_libre':
            return {
                'status': 'applied',
                'ticket_id': ticket_id,
                'action': action,
                'hint': 'Écris ta réponse libre dans ce fil 👇',
            }
        elif action == 'choix_qcm':
            values = data.get('values') or []
            choice = str(values[0]) if values else ''
            if not choice:
                return {'status': 'error', 'error': 'choix_manquant'}
            if choice == '__autre__':
                discuss(connection, ticket_id)
            else:
                decide(
                    connection, ticket_id, 'APPROVED', note=f'QCM : {choice}'
                )
        else:
            return {'status': 'error', 'error': f'action_inconnue:{action}'}
    except TicketError as exc:
        return {'status': 'error', 'error': str(exc)}
    if decision_id:
        _stamp(
            connection,
            ticket_id,
            action,
            decision_id,
            {'item': item_id} if item_id else None,
        )
    return {'status': 'applied', 'ticket_id': ticket_id, 'action': action}
