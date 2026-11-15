#!/usr/bin/env python3
"""Demander à Julien ce qui manque : un ticket REQUESTED, qui gèle la tâche.

Une invocation qui ne peut pas faire ce qu'on lui demande (pas d'outil,
pas d'accès, une information qu'elle n'a pas) appelle « Demander une
nouvelle capacité » plutôt que d'inventer. Le ticket dit en bref ce qu'elle
demande, puis le détail, aussi long qu'il le faut, et pourquoi.

Appelée pendant une tâche, la demande la **gèle** (``gel``) : la tâche
n'écrit rien et attend la réponse de Julien, sans limite de temps. Sa
réponse (un texte libre, ou « Faire sans ») la fait repartir du début, avec
la réponse dans ses paramètres (``serge/tickets/reponses.py``).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.tickets.lifecycle import create_ticket, publish
from serge.tickets.types import ticket_types

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
    resume: str = '',
    task_id: str = '',
    types: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pose (ou réutilise) un ticket REQUESTED.

    Args:
        conn: Canon (commit par l’appelant).
        besoin: Ce qui manque, en détail (aussi long qu'il le faut).
        point: Invocation appelante.
        contexte: Pourquoi.
        resume: Ce qui est demandé, en une phrase simple (le titre).
        task_id: La tâche qui demande : elle sera gelée (``gel``).
        types: Registre tickets (tests).

    Returns:
        ``ticket_id``, ``type``, ``deja`` si déjà ouvert, ``gel`` si la
        tâche doit attendre la réponse.

    Raises:
        CapaciteError: Besoin vide.
    """
    texte = besoin.strip()
    if not texte:
        raise CapaciteError('besoin vide')
    point_id = str(point or '').strip()
    en_bref = resume.strip() or texte
    found = _deja_ouvert(conn, texte, point_id, task_id)
    if found:
        ticket_id, deja = found, True
    else:
        registre = types if types is not None else ticket_types(conn)
        ticket_id = create_ticket(
            conn,
            registre,
            'REQUESTED',
            en_bref[:TITRE_MAX],
            {
                'en_bref': en_bref,
                'demande': texte,
                'contexte': contexte.strip(),
                'point_llm': point_id,
            },
            creator=f'llm:{point_id}' if point_id else 'serge',
        )
        if task_id:
            # La réponse fera repartir cette tâche.
            conn.execute(
                "UPDATE tickets SET ref_table='tasks', ref_id=? WHERE id=?",
                (task_id, ticket_id),
            )
        publish(conn, ticket_id)
        deja = False
    out = {
        'ok': True,
        'ticket_id': ticket_id,
        'type': 'REQUESTED',
        'deja': deja,
    }
    if task_id:
        out['gel'] = True
        out['detail'] = 'la tâche attend la réponse de Julien'
    return out


def _deja_ouvert(
    conn: sqlite3.Connection, besoin: str, point: str, task_id: str
) -> str | None:
    """Id du ticket ouvert identique (même tâche s'il y en a une), ou None."""
    marqueurs = ','.join('?' * len(OUVERTS))
    rows = conn.execute(
        "SELECT id, payload_json, ref_id FROM tickets WHERE type='REQUESTED'"
        f' AND state IN ({marqueurs})',
        tuple(sorted(OUVERTS)),
    ).fetchall()
    for ident, raw, ref in rows:
        try:
            data = json.loads(raw or '{}')
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or str(ref or '') != task_id:
            continue
        if data.get('demande') == besoin and data.get('point_llm') == point:
            return str(ident)
    return None
