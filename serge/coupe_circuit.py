#!/usr/bin/env python3
"""Coupe-circuits : heartbeat ordonnanceur + kinds (flags runtime)."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.db.store import utcnow
from serge.etapes import (
    ETAPE_IDS,
    SEED,
    EtapeError,
    ensure_pipeline_steps,
    set_etape_marche,
)

CIBLES = frozenset({'serge', 'etape', 'kind'})
FLAG_HEARTBEAT = 'scheduler.heartbeat'


class CoupeError(ValueError):
    """Cible, étape ou kind hors enum."""


def _flag_kind(kind: str) -> str:
    return f'kind.{kind}'


def _est_kill(
    conn: sqlite3.Connection, name: str, now: str | None = None
) -> bool:
    moment = now or utcnow()
    row = conn.execute(
        'SELECT value, expires_at FROM runtime_flags WHERE name=?',
        (name,),
    ).fetchone()
    if row is None:
        return False
    if str(row[1] or '') and str(row[1]) <= moment:
        return False
    return str(row[0]) == 'kill'


def _poser(
    conn: sqlite3.Connection,
    name: str,
    *,
    coupe: bool,
    now: str | None = None,
) -> None:
    moment = now or utcnow()
    if coupe:
        conn.execute(
            'INSERT OR REPLACE INTO runtime_flags(name, value, set_by,'
            " set_at, expires_at, reason) VALUES(?, 'kill', 'owner', ?, '',"
            " 'coupe-circuit MC')",
            (name, moment),
        )
        return
    conn.execute('DELETE FROM runtime_flags WHERE name=?', (name,))


def heartbeat_marche(conn: sqlite3.Connection, now: str | None = None) -> bool:
    """True si l’ordonnanceur peut prendre une tâche.

    Args:
        conn: Canon.
        now: ISO UTC (défaut : horloge).

    Returns:
        False si le heartbeat est coupé.
    """
    return not _est_kill(conn, FLAG_HEARTBEAT, now)


def kinds_interrompus(
    conn: sqlite3.Connection, now: str | None = None
) -> frozenset[str]:
    """Kinds coupés un par un (indépendant des sacs).

    Args:
        conn: Canon.
        now: ISO UTC (défaut : horloge).

    Returns:
        Ensemble de kinds (vide si tous marchent).
    """
    return frozenset(
        kind
        for _ident, _rang, kinds in SEED
        for kind in kinds
        if _est_kill(conn, _flag_kind(kind), now)
    )


def set_heartbeat(
    conn: sqlite3.Connection, marche: bool, now: str | None = None
) -> dict[str, Any]:
    """Coupe ou remet le heartbeat de l’ordonnanceur.

    Args:
        conn: Canon (commit par l’appelant).
        marche: True = le cycle peut claim.
        now: ISO UTC (défaut : horloge).

    Returns:
        ``{cible, marche}``.
    """
    _poser(conn, FLAG_HEARTBEAT, coupe=not marche, now=now)
    return {'cible': 'serge', 'marche': heartbeat_marche(conn, now)}


def set_kind_marche(
    conn: sqlite3.Connection,
    kind: str,
    marche: bool,
    now: str | None = None,
) -> dict[str, Any]:
    """Coupe ou remet un kind, toutes étapes confondues.

    Args:
        conn: Canon (commit par l’appelant).
        kind: Kind du seed (`KIND_DEFAUT`).
        marche: True = l’ordonnanceur accepte ce kind.
        now: ISO UTC (défaut : horloge).

    Returns:
        ``{cible, id, marche}``.

    Raises:
        CoupeError: Kind hors enum.
    """
    connus = {k for _i, _r, ks in SEED for k in ks}
    if kind not in connus:
        raise CoupeError(f'kind inconnu : {kind}')
    _poser(conn, _flag_kind(kind), coupe=not marche, now=now)
    return {
        'cible': 'kind',
        'id': kind,
        'marche': kind not in kinds_interrompus(conn, now),
    }


def appliquer_coupe(
    conn: sqlite3.Connection, cible: str, ident: str, marche: bool
) -> dict[str, Any]:
    """Applique un coupe-circuit (enum fermé).

    Args:
        conn: Canon (commit par l’appelant).
        cible: ``serge``, ``etape`` ou ``kind``.
        ident: Id d’étape ou de kind (ignoré pour Serge).
        marche: True = en marche.

    Returns:
        Dict typé selon la cible.

    Raises:
        CoupeError: Cible, étape ou kind hors enum.
    """
    if cible not in CIBLES:
        raise CoupeError(f'cible inconnue : {cible}')
    if cible == 'serge':
        return set_heartbeat(conn, marche)
    if cible == 'etape':
        try:
            etat = set_etape_marche(conn, ident, marche)
        except EtapeError as exc:
            raise CoupeError(str(exc)) from exc
        return {'cible': 'etape', **etat}
    return set_kind_marche(conn, ident, marche)


def etat_coupes(
    conn: sqlite3.Connection, now: str | None = None
) -> dict[str, Any]:
    """État des trois nappes de coupe-circuits (MC Live).

    Args:
        conn: Canon (peut semer les étapes).
        now: ISO UTC (défaut : horloge).

    Returns:
        ``{serge, etapes, kinds}``.
    """
    ensure_pipeline_steps(conn)
    etapes: list[dict[str, Any]] = []
    for row in conn.execute(
        'SELECT id, titre, enabled FROM pipeline_steps ORDER BY rang, id'
    ):
        ident = str(row[0])
        if ident not in ETAPE_IDS:
            continue
        etapes.append(
            {
                'id': ident,
                'titre': str(row[1] or ident),
                'marche': bool(row[2]),
            }
        )
    morts = kinds_interrompus(conn, now)
    kinds: list[dict[str, Any]] = []
    for ident, _rang, ks in SEED:
        for kind in ks:
            kinds.append(
                {
                    'id': kind,
                    'marche': kind not in morts,
                    'etape_id': ident,
                }
            )
    return {
        'serge': heartbeat_marche(conn, now),
        'etapes': etapes,
        'kinds': kinds,
    }
