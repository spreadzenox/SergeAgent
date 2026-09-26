#!/usr/bin/env python3
"""Demander une capacité manquante : ticket REQUESTED, pas d’invention."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.registry import load_ticket_types
from serge.tickets.lifecycle import create_ticket, publish

OUVERTS = frozenset({'DRAFT', 'OPEN', 'DISCUSSING'})
TITRE_MAX = 80


class CapaciteError(ValueError):
    """Besoin vide."""


def poser_demande(
    conn: sqlite3.Connection,
    besoin: str,
    *,
    point: str = '',
    contexte: str = '',
    types: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pose (ou réutilise) un ticket REQUESTED.

    Args:
        conn: Canon (commit par l’appelant).
        besoin: Ce qui manque (canal, outil, acte).
        point: Jugement appelant.
        contexte: Pourquoi, une phrase.
        types: Registre tickets (tests).

    Returns:
        ``ticket_id``, ``type``, ``deja`` si déjà ouvert.

    Raises:
        CapaciteError: Besoin vide.
    """
    texte = besoin.strip()
    if not texte:
        raise CapaciteError('besoin vide')
    point_id = str(point or '').strip()
    note = contexte.strip()
    found = _deja_ouvert(conn, texte, point_id)
    if found:
        return {
            'ok': True,
            'ticket_id': found,
            'type': 'REQUESTED',
            'deja': True,
        }
    registre = types if types is not None else load_ticket_types()
    ticket_id = create_ticket(
        conn,
        registre,
        'REQUESTED',
        texte[:TITRE_MAX],
        {
            'demande': texte,
            'contexte': note,
            'point_llm': point_id,
        },
        creator=f'llm:{point_id}' if point_id else 'serge',
    )
    publish(conn, ticket_id)
    return {
        'ok': True,
        'ticket_id': ticket_id,
        'type': 'REQUESTED',
        'deja': False,
    }


def _deja_ouvert(
    conn: sqlite3.Connection, besoin: str, point: str
) -> str | None:
    """Id du ticket ouvert identique, ou None."""
    marqueurs = ','.join('?' * len(OUVERTS))
    rows = conn.execute(
        "SELECT id, payload_json FROM tickets WHERE type='REQUESTED'"
        f' AND state IN ({marqueurs})',
        tuple(sorted(OUVERTS)),
    ).fetchall()
    for ident, raw in rows:
        try:
            data = json.loads(raw or '{}')
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        if data.get('demande') == besoin and data.get('point_llm') == point:
            return str(ident)
    return None
