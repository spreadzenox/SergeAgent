#!/usr/bin/env python3
"""Projecteurs P3 Décisions : liste, carte, diffs, MEMORY, métriques, digest."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_outils import apres_iso
from serge.points.interact import strip_ids
from serge.policy import PolicyError
from serge.registry import load_ticket_types
from serge.tickets import champs_carte, get_ticket
from serge.tickets.lifecycle import OPENISH
from serge.tickets.shared import TicketError

BOUTONS_MC = frozenset({'approuver', 'rejeter', 'editer', 'discuter'})


def _types() -> dict:
    try:
        return load_ticket_types()
    except PolicyError:
        return {}


def _est_urgent(typ: str, etat: str, expiry: str, now: str) -> bool:
    # Miroir project_urgents (règle) : GUICHET <15min, veto <1h, ALERT.
    if etat not in OPENISH:
        return False
    if typ == 'ALERT':
        return True
    if not expiry:
        return False
    if typ == 'GUICHET':
        return expiry < apres_iso(now, minutes=15)
    if typ == 'VETO_AMONT':
        return expiry < apres_iso(now, minutes=60)
    return False


def _boutons(spec: Any) -> list[str]:
    if not isinstance(spec, dict):
        return []
    return [b for b in (spec.get('buttons') or []) if b in BOUTONS_MC]


def project_tickets(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Liste tickets : ouverts d'abord, récents d'abord, cap 50 (P3).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC (flag urgent).

    Returns:
        Dict {items: [{id, type, titre, etat, expiry_at, boutons,
        urgent}]} (filtres/recherche/tri côté client).
    """
    _ = policy
    types = _types()
    items = []
    for row in conn.execute(
        'SELECT id, type, title, state, expiry_at FROM tickets ORDER BY'
        " CASE state WHEN 'OPEN' THEN 0 WHEN 'DISCUSSING' THEN 1"
        " WHEN 'DRAFT' THEN 2 ELSE 3 END, updated_at DESC LIMIT 50"
    ).fetchall():
        typ = str(row[1])
        etat = str(row[3])
        expiry = str(row[4])
        items.append(
            {
                'id': str(row[0]),
                'type': typ,
                'titre': strip_ids(str(row[2])),
                'etat': etat,
                'expiry_at': expiry,
                'boutons': _boutons(types.get(typ)),
                'urgent': _est_urgent(typ, etat, expiry, now),
            }
        )
    return {'items': items}


def project_carte(
    conn: sqlite3.Connection, ticket_id: str
) -> dict[str, Any] | None:
    """Carte §17 : champs registre + boutons + items + historique (P3).

    Args:
        conn: Connexion canon (lecture).
        ticket_id: Ticket visé.

    Returns:
        Dict carte ou None si ticket inconnu (endpoint 404).
    """
    try:
        ticket = get_ticket(conn, ticket_id)
    except TicketError:
        return None
    spec = _types().get(str(ticket.get('type')), {})
    if not isinstance(spec, dict):
        spec = {}
    try:
        raw = json.loads(ticket.get('versions_json') or '[]')
    except ValueError:
        raw = []
    versions = []
    if isinstance(raw, list):
        for entry in raw:
            if isinstance(entry, dict):
                versions.append(
                    {
                        'n': entry.get('n'),
                        'note': entry.get('note'),
                        'at': entry.get('at'),
                    }
                )
    return {
        'ticket': {
            'id': ticket_id,
            'type': str(ticket.get('type')),
            'titre': strip_ids(str(ticket.get('title'))),
            'etat': str(ticket.get('state')),
            'expiry_at': str(ticket.get('expiry_at')),
            'defaut': str(ticket.get('default_action') or ''),
            'defaut_detail': str(spec.get('default_detail') or ''),
        },
        'champs': [
            {'titre': cle, 'texte': strip_ids(texte)}
            for cle, texte in champs_carte(ticket, spec)
        ],
        'boutons': _boutons(spec),
        'items_actes': list(spec.get('items_per_lesson') or []),
        'items': [
            {
                'id': str(item.get('id')),
                'kind': str(item.get('kind')),
                'label': strip_ids(str(item.get('label'))),
                'etat': str(item.get('state')),
            }
            for item in ticket.get('items') or []
        ],
        'events': [
            {
                'ts': str(event.get('ts')),
                'acteur': str(event.get('actor')),
                'kind': str(event.get('kind')),
            }
            for event in ticket.get('events') or []
        ],
        'versions': versions,
    }
