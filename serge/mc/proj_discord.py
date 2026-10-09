#!/usr/bin/env python3
"""Projecteurs P3 Décisions : administrateurs Discord, types de tickets.

Décisions Q85 et Q86 : chaque ticket part en message privé à chaque
administrateur ; les délais, décisions par défaut et boutons des types de
tickets se règlent ici.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.tickets.acts import BOUTONS
from serge.tickets.admins import admins
from serge.tickets.types import ticket_types


def project_admins_discord(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les administrateurs Discord de Serge.

    Returns:
        Dict {admins: [{user_id, name, added_at}]}.
    """
    _ = (policy, now)
    return {
        'admins': [
            {k: a[k] for k in ('user_id', 'name', 'added_at')}
            for a in admins(conn)
        ]
    }


def project_types_tickets(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les types de tickets et ce qui s'en règle.

    Returns:
        Dict {types: [{id, role, emoji, expiry_minutes, default_detail,
        buttons}], boutons_possibles: [...]}.
    """
    _ = (policy, now)
    return {
        'types': [
            {
                'id': ident,
                'role': str(spec.get('role') or ''),
                'emoji': str((spec.get('render') or {}).get('emoji') or ''),
                'expiry_minutes': spec.get('expiry_minutes'),
                'default_detail': str(spec.get('default_detail') or ''),
                'buttons': list(spec.get('buttons') or []),
            }
            for ident, spec in ticket_types(conn).items()
        ],
        'boutons_possibles': sorted(BOUTONS),
    }
