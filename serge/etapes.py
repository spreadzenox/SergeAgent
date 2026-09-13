#!/usr/bin/env python3
"""Étapes du pipe : mapping kinds + interrupteur (table pipeline_steps)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# Semence : ids stables (carte Live). kinds = ce que l’ordonnanceur coupe.
SEED: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ('ecoute', 0, ('listen.collect', 'listen.cluster')),
    ('hypothese', 1, ()),
    ('test', 2, ('email.send', 'voice.send')),
    ('qualif', 3, ()),
    (
        'conversation',
        4,
        (
            'inbound.classify',
            'inbound.reply_priority',
            'inbound.judge_other',
            'email.poll',
            'voice.score',
        ),
    ),
    ('intent', 5, ()),
    ('caisse', 6, ()),
)


class EtapeError(ValueError):
    """Étape inconnue ou payload invalide."""


def ensure_pipeline_steps(conn: sqlite3.Connection) -> None:
    """Pose les 7 étapes ; met à jour les kinds, jamais ``enabled``.

    Args:
        conn: Canon (commit par l’appelant).
    """
    for ident, rang, kinds in SEED:
        blob = json.dumps(list(kinds), ensure_ascii=False)
        conn.execute(
            'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang)'
            ' VALUES(?,?,?,?)'
            ' ON CONFLICT(id) DO UPDATE SET'
            ' kinds_json=excluded.kinds_json, rang=excluded.rang',
            (ident, 1, blob, rang),
        )


def etats_etapes(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """État de toutes les étapes (semence si table vide).

    Args:
        conn: Canon (lecture, éventuellement semence).

    Returns:
        ``{id: {marche, kinds, rang}}``.
    """
    ensure_pipeline_steps(conn)
    rows = conn.execute(
        'SELECT id, enabled, kinds_json, rang FROM pipeline_steps'
        ' ORDER BY rang, id'
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        kinds = _kinds(row[2])
        out[str(row[0])] = {
            'marche': bool(row[1]),
            'kinds': kinds,
            'rang': int(row[3]),
        }
    return out


def kinds_coupes(conn: sqlite3.Connection) -> frozenset[str]:
    """Kinds dont l’étape est coupée — l’ordonnanceur ne les réclame pas.

    Args:
        conn: Canon.

    Returns:
        Ensemble de kinds bloqués (vide si tout est en marche).
    """
    blocked: set[str] = set()
    for spec in etats_etapes(conn).values():
        if not spec['marche']:
            blocked.update(spec['kinds'])
    return frozenset(blocked)


def set_etape_marche(
    conn: sqlite3.Connection, ident: str, marche: bool
) -> dict[str, Any]:
    """Coupe ou remet en marche une étape.

    Args:
        conn: Canon (commit par l’appelant).
        ident: Id d’étape (``ecoute``, ``test``, …).
        marche: True = l’ordonnanceur accepte les kinds.

    Returns:
        ``{id, marche, kinds}``.

    Raises:
        EtapeError: Id inconnu.
    """
    ensure_pipeline_steps(conn)
    cursor = conn.execute(
        'UPDATE pipeline_steps SET enabled=? WHERE id=?',
        (1 if marche else 0, ident),
    )
    if not cursor.rowcount:
        raise EtapeError(f'étape inconnue : {ident}')
    spec = etats_etapes(conn)[ident]
    return {'id': ident, 'marche': spec['marche'], 'kinds': spec['kinds']}


def _kinds(raw: object) -> list[str]:
    if isinstance(raw, list):
        data = raw
    else:
        try:
            data = json.loads(str(raw or '[]'))
        except (TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if item]
