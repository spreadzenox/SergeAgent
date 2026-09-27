#!/usr/bin/env python3
"""Les coupe-circuits : démarrer Serge, couper une étape, une file ou une invocation.

- **Serge** est **arrêté par défaut**. Il ne tourne que si quelqu'un l'a
  démarré dans Mission Control (drapeau ``scheduler.heartbeat`` à ``on``
  dans ``runtime_flags``). Arrêté, les files ne créent ni ne prennent de
  tâche, et la voix ne décroche pas et n'appelle pas. Une instance neuve,
  ou un déploiement, ne démarre donc jamais Serge tout seul.
- **Une étape** : ses invocations ne tournent plus
  (``pipeline_steps.enabled``).
- **Une file** : ``conversations`` ou ``works`` ne prend plus de tâche
  (``queues.enabled``).
- **Une invocation** : ses tâches attendent (``invocations.enabled``).

Tout est en base : couper dans Mission Control agit au tour suivant de
chaque file, sans redémarrage.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.etapes import (
    ETAPE_IDS,
    EtapeError,
    ensure_pipeline_steps,
    set_etape_marche,
)

CIBLES = frozenset({'serge', 'etape', 'file', 'invocation'})
FLAG_HEARTBEAT = 'scheduler.heartbeat'


class CoupeError(ValueError):
    """Cible, étape, file ou invocation inconnue."""


def heartbeat_marche(conn: sqlite3.Connection, now: str | None = None) -> bool:
    """Vrai seulement si Serge a été démarré dans Mission Control.

    Args:
        conn: Connexion à la base.
        now: ISO UTC (défaut : horloge). Un démarrage expiré ne compte plus.
    """
    moment = now or utcnow()
    row = conn.execute(
        'SELECT value, expires_at FROM runtime_flags WHERE name=?',
        (FLAG_HEARTBEAT,),
    ).fetchone()
    if row is None or str(row[0]) != 'on':
        return False
    return not (str(row[1] or '') and str(row[1]) <= moment)


def serge_demarre(path: Path | None = None) -> bool:
    """L'interrupteur, lu par un programme hors des files (la voix).

    La base est ouverte en lecture seule. Base absente ou illisible :
    Serge est considéré comme arrêté.

    Args:
        path: Chemin de la base (défaut : celle de l'instance).
    """
    from serge.db.store import default_canon_path

    target = path or default_canon_path()
    try:
        conn = sqlite3.connect(f'file:{target}?mode=ro', uri=True, timeout=5)
    except sqlite3.Error:
        return False
    try:
        return heartbeat_marche(conn)
    except sqlite3.Error:
        return False
    finally:
        conn.close()


def set_heartbeat(
    conn: sqlite3.Connection, marche: bool, now: str | None = None
) -> dict[str, Any]:
    """Démarre ou arrête Serge.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        marche: True = les files prennent des tâches, la voix décroche.
        now: ISO UTC (défaut : horloge).

    Returns:
        ``{cible, marche}``.
    """
    moment = now or utcnow()
    if marche:
        conn.execute(
            'INSERT OR REPLACE INTO runtime_flags(name, value, set_by,'
            " set_at, expires_at, reason) VALUES(?, 'on', 'owner', ?, '',"
            " 'démarré dans Mission Control')",
            (FLAG_HEARTBEAT, moment),
        )
    else:
        conn.execute(
            'DELETE FROM runtime_flags WHERE name=?', (FLAG_HEARTBEAT,)
        )
    return {'cible': 'serge', 'marche': heartbeat_marche(conn, now)}


def _set_enabled(
    conn: sqlite3.Connection, table: str, ident: str, marche: bool
) -> bool:
    """Pose ``enabled`` sur une file ou une invocation. Faux si inconnue."""
    extra = ''
    params: tuple[Any, ...] = (int(marche), ident)
    if table == 'invocations':
        extra = ", updated_at=?, updated_by='mc'"
        params = (int(marche), utcnow(), ident)
    cursor = conn.execute(
        f'UPDATE {table} SET enabled=?{extra} WHERE id=?', params
    )
    return cursor.rowcount == 1


def appliquer_coupe(
    conn: sqlite3.Connection, cible: str, ident: str, marche: bool
) -> dict[str, Any]:
    """Applique un coupe-circuit.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        cible: ``serge``, ``etape``, ``file`` ou ``invocation``.
        ident: Id visé (ignoré pour Serge).
        marche: True = en marche.

    Returns:
        ``{cible, marche}``, plus ``id`` sauf pour Serge.

    Raises:
        CoupeError: Cible ou id inconnu.
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
    table = 'queues' if cible == 'file' else 'invocations'
    if not _set_enabled(conn, table, ident, marche):
        raise CoupeError(f'{cible} inconnue : {ident}')
    return {'cible': cible, 'id': ident, 'marche': marche}


def etat_coupes(
    conn: sqlite3.Connection, now: str | None = None
) -> dict[str, Any]:
    """L'état de tous les coupe-circuits, pour Mission Control.

    Args:
        conn: Connexion à la base.
        now: ISO UTC (défaut : horloge).

    Returns:
        ``{serge, etapes, files, invocations}`` ; chaque élément a ``id``,
        ``titre`` et ``marche`` (et ``etape_id`` pour une invocation).
    """
    ensure_pipeline_steps(conn)
    etapes = [
        {'id': str(r[0]), 'titre': str(r[1] or r[0]), 'marche': bool(r[2])}
        for r in conn.execute(
            'SELECT id, titre, enabled FROM pipeline_steps ORDER BY rang, id'
        ).fetchall()
        if str(r[0]) in ETAPE_IDS
    ]
    files = [
        {'id': str(r[0]), 'titre': str(r[1] or r[0]), 'marche': bool(r[2])}
        for r in conn.execute(
            'SELECT id, title, enabled FROM queues ORDER BY id'
        ).fetchall()
    ]
    invocations = [
        {
            'id': str(r[0]),
            'titre': str(r[1] or r[0]),
            'marche': bool(r[2]),
            'etape_id': str(r[3]),
        }
        for r in conn.execute(
            'SELECT i.id, i.title, i.enabled, i.step_id FROM invocations i'
            ' LEFT JOIN pipeline_steps s ON s.id=i.step_id'
            " WHERE i.deleted_at='' ORDER BY COALESCE(s.rang, 99), i.id"
        ).fetchall()
    ]
    return {
        'serge': heartbeat_marche(conn, now),
        'etapes': etapes,
        'files': files,
        'invocations': invocations,
    }
