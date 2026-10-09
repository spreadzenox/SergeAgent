#!/usr/bin/env python3
"""Interactions Discord → actes tickets (boutons = actes typés).

Un bouton a pour custom_id ``t:<ticket>:<action>[:<item>]``, une fenêtre de
saisie ``m:<ticket>:<action>``. Seul un administrateur de Serge (en base,
décision Q86) peut agir ; l'acte est noté à son nom (``discord:<id>``), et
dédoublonné par l'id de l'interaction. Un bouton qui demande un texte
(« Éditer », « Réponse libre », « Discuter », « Autre » d'un choix) ouvre
une fenêtre de saisie. Le LLM n'est jamais sur le chemin d'une décision.
Un refus est un message éphémère, en français.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.tickets.acts import APPROVE, DISCUTER, EDITER, REJECT, REPONDRE
from serge.tickets.admins import is_admin
from serge.tickets.items import set_item, tout_approuver
from serge.tickets.lifecycle import decide, discuss
from serge.tickets.reponses import noter_reponse
from serge.tickets.shared import TicketError, already_applied, record_event

ITEM_STATES = {'garder': 'keep', 'modifier': 'edit', 'jeter': 'drop'}
# Les boutons qui demandent un texte : le titre de leur fenêtre de saisie,
# et celui de son champ.
SAISIES = {
    'editer': ('Modifier', 'Ce qu’il faut changer'),
    'reponse_libre': ('Ta réponse', 'Ta réponse'),
    'choix_qcm': ('Autre réponse', 'Ta réponse'),
    'discuter': ('Discuter', 'Ton message'),
    'discuter_fil': ('Discuter', 'Ton message'),
    'ma_reponse': ('Ta réponse au contact', 'Le message qui partira'),
    'reecrire': ('Réécrire le brouillon', 'Tes consignes à Serge'),
}
# Les types d'interaction Discord : un composant, une fenêtre envoyée.
COMPOSANT = frozenset({2, 3})
FENETRE = 5


def parse_custom_id(
    custom_id: str, prefix: str = 't'
) -> tuple[str, str, str] | None:
    """Parse ``<prefix>:<ticket>:<action>[:<item>]`` (None si malformé).

    Args:
        custom_id: custom_id du composant ou de la fenêtre Discord.
        prefix: ``t`` pour un bouton, ``m`` pour une fenêtre de saisie.

    Returns:
        Tuple (ticket_id, action, item_id?) ou None.
    """
    parts = (custom_id or '').split(':')
    if len(parts) not in {3, 4} or parts[0] != prefix:
        return None
    ticket_id, action = parts[1], parts[2]
    if not ticket_id or not action:
        return None
    return (ticket_id, action, parts[3] if len(parts) == 4 else '')


def actor_id(interaction: Mapping[str, Any]) -> str:
    """Snowflake auteur (member.user.id en salon, user.id en message privé).

    Args:
        interaction: Objet interaction Discord.

    Returns:
        L'id auteur, ``''`` s'il manque.
    """
    member = interaction.get('member') or {}
    user = member.get('user') or interaction.get('user') or {}
    return str(user.get('id') or '')


def fenetre(ticket_id: str, action: str) -> dict[str, Any]:
    """La fenêtre de saisie d'un bouton qui demande un texte."""
    titre, champ = SAISIES[action]
    return {
        'custom_id': f'm:{ticket_id}:{action}',
        'title': titre,
        'components': [
            {
                'type': 1,
                'components': [
                    {
                        'type': 4,
                        'custom_id': 'texte',
                        'style': 2,
                        'label': champ,
                        'required': True,
                        'max_length': 2000,
                    }
                ],
            }
        ],
    }


def _texte(data: Mapping[str, Any]) -> str:
    """Le texte saisi dans une fenêtre."""
    for row in data.get('components') or []:
        for field in row.get('components') or []:
            if field.get('custom_id') == 'texte':
                return str(field.get('value') or '').strip()
    return ''


def _stamp(
    connection: sqlite3.Connection,
    ticket_id: str,
    action: str,
    actor: str,
    decision_id: str,
    extra: dict[str, Any] | None = None,
) -> None:
    record_event(
        connection,
        ticket_id,
        actor,
        f'discord.{action}',
        {'decision_id': decision_id, **(extra or {})},
    )


def _saisie(
    connection: sqlite3.Connection,
    ticket_id: str,
    action: str,
    texte: str,
    actor: str,
) -> dict[str, Any] | None:
    """Applique le texte d'une fenêtre ; rend une erreur, ou None."""
    if not texte:
        return {'status': 'error', 'error': 'texte_vide'}
    if action in EDITER:
        decide(connection, ticket_id, 'EDITED', actor=actor, note=texte)
    elif action in REPONDRE:
        decide(connection, ticket_id, 'APPROVED', actor=actor, note=texte)
    elif action in DISCUTER:
        discuss(connection, ticket_id, actor=actor)
        record_event(
            connection, ticket_id, actor, 'discord.fil', {'message': texte}
        )
    else:
        return {'status': 'error', 'error': f'action_inconnue:{action}'}
    return None


def _bouton(
    connection: sqlite3.Connection,
    data: Mapping[str, Any],
    ticket_id: str,
    action: str,
    item_id: str,
    actor: str,
) -> dict[str, Any] | None:
    """Applique un bouton ; rend une fenêtre à ouvrir, une erreur, ou None."""
    if action in APPROVE:
        if action == 'tout_approuver':
            tout_approuver(connection, ticket_id)
        decide(connection, ticket_id, 'APPROVED', actor=actor)
    elif action in REJECT:
        decide(connection, ticket_id, 'REJECTED', actor=actor)
    elif action in ITEM_STATES:
        if not item_id:
            return {'status': 'error', 'error': 'item_manquant'}
        set_item(connection, item_id, ITEM_STATES[action])
    elif action == 'accuse_reception':
        pass
    elif action == 'choix_qcm':
        values = data.get('values') or []
        choice = str(values[0]) if values else ''
        if not choice:
            return {'status': 'error', 'error': 'choix_manquant'}
        if choice == '__autre__':
            return {'status': 'modal', 'modal': fenetre(ticket_id, action)}
        decide(
            connection,
            ticket_id,
            'APPROVED',
            actor=actor,
            note=f'QCM : {choice}',
        )
    elif action in SAISIES:
        return {'status': 'modal', 'modal': fenetre(ticket_id, action)}
    else:
        return {'status': 'error', 'error': f'action_inconnue:{action}'}
    return None


def route_interaction(
    connection: sqlite3.Connection, interaction: Mapping[str, Any]
) -> dict[str, Any]:
    """Route un bouton, un choix ou une fenêtre envoyée vers un acte ticket.

    Args:
        connection: Connexion canon (commit par l'appelant).
        interaction: Objet Discord (id, type, token, member/user, data).

    Returns:
        Dict status applied|modal|duplicate|refused|error (+ ticket,
        action, fenêtre à ouvrir, message).
    """
    data = interaction.get('data') or {}
    saisie = int(interaction.get('type') or 0) == FENETRE
    parsed = parse_custom_id(
        str(data.get('custom_id') or ''), 'm' if saisie else 't'
    )
    if parsed is None:
        return {'status': 'error', 'error': 'custom_id_malforme'}
    ticket_id, action, item_id = parsed
    user = actor_id(interaction)
    if not user or not is_admin(connection, user):
        return {
            'status': 'refused',
            'error': 'admin_only',
            'message': 'Réservé aux administrateurs de Serge.',
        }
    actor = f'discord:{user}'
    decision_id = str(interaction.get('id') or '')
    if decision_id and already_applied(connection, ticket_id, decision_id):
        return {'status': 'duplicate', 'ticket_id': ticket_id}
    try:
        result = (
            _saisie(connection, ticket_id, action, _texte(data), actor)
            if saisie
            else _bouton(connection, data, ticket_id, action, item_id, actor)
        )
    except TicketError as exc:
        return {'status': 'error', 'error': str(exc)}
    if result is not None:
        return {**result, 'ticket_id': ticket_id, 'action': action}
    # La réponse réveille les invocations réglées en base (Q85).
    texte = _texte(data) if saisie else ''
    if not saisie and action == 'choix_qcm':
        texte = str((data.get('values') or [''])[0])
    noter_reponse(connection, ticket_id, action, texte, actor)
    if decision_id:
        _stamp(
            connection,
            ticket_id,
            action,
            actor,
            decision_id,
            {'item': item_id} if item_id else None,
        )
    return {'status': 'applied', 'ticket_id': ticket_id, 'action': action}
