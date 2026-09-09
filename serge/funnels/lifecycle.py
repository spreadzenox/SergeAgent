#!/usr/bin/env python3
"""Lifecycle ventures (B §1) : états, gates, une seule ACTIVE.

CANDIDATE → SMOKE_READY → SMOKE_RUNNING → SMOKE_DONE → FULL_READY →
FULL_RUNNING → SCALE | PIVOT | EXTEND | KILLED | INVALID_RETRY.
Gates : campagne READY (runs), hypothèse full approuvée + canary 1 €
réussi (full). Chaque transition = événement. Le lifecycle VÉRIFIE ;
l'allocteur/séquenceur crée tickets et campagnes.
"""

from __future__ import annotations

import sqlite3
import uuid

from serge.db.store import append_event, utcnow

ACTIVE = frozenset({'SMOKE_RUNNING', 'FULL_RUNNING', 'SCALE'})


class VentureError(ValueError):
    pass


def _new_id() -> str:
    return f'v_{uuid.uuid4().hex[:12]}'


def _get(conn: sqlite3.Connection, venture_id: str) -> sqlite3.Row:
    row = conn.execute(
        'SELECT id, lifecycle, schedulable FROM ventures WHERE id=?',
        (venture_id,),
    ).fetchone()
    if not row:
        raise VentureError(f'venture inconnue : {venture_id}')
    return row


def _move(
    conn: sqlite3.Connection,
    venture_id: str,
    allowed_from: frozenset[str],
    to_state: str,
    schedulable: int | None = None,
) -> None:
    row = _get(conn, venture_id)
    if row['lifecycle'] not in allowed_from:
        raise VentureError(
            f'{venture_id} : {row["lifecycle"]} → {to_state} interdit'
        )
    if to_state in ACTIVE:
        blocker = conn.execute(
            'SELECT id FROM ventures WHERE schedulable=1 AND id<>?'
            f' AND lifecycle IN ({",".join("?" * len(ACTIVE))})',
            (venture_id, *sorted(ACTIVE)),
        ).fetchone()
        if blocker:
            raise VentureError(
                f'venture ACTIVE existante : {blocker[0]} (une seule à la fois)'
            )
    if schedulable is None:
        schedulable = 1 if to_state in ACTIVE else 0
    conn.execute(
        'UPDATE ventures SET lifecycle=?, schedulable=?, updated_at=?'
        ' WHERE id=?',
        (to_state, schedulable, utcnow(), venture_id),
    )
    append_event(
        conn,
        actor='lifecycle',
        type=f'venture.{to_state.lower()}',
        venture_id=venture_id,
        payload={'from': row['lifecycle']},
    )


def _ready_campaign(conn: sqlite3.Connection, venture_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM campaigns WHERE venture_id=? AND state='READY'",
        (venture_id,),
    ).fetchone()
    return row is not None


def collect_ready(conn: sqlite3.Connection, venture_id: str) -> bool:
    """Caisse prête v1 : canary 1 € réussi (catalogue+capacités suivent).

    Args:
        conn: Connexion canon (lecture).
        venture_id: Venture testée.

    Returns:
        True si un canary a réussi pour cette venture.
    """
    row = conn.execute(
        "SELECT 1 FROM transactions WHERE venture_id=? AND kind='canary'"
        " AND status='succeeded'",
        (venture_id,),
    ).fetchone()
    return row is not None


def approved_full_hypothesis(
    conn: sqlite3.Connection, venture_id: str
) -> bool:
    """Hypothèse full approuvée (ticket HYPOTHESIS, payload lié).

    Args:
        conn: Connexion canon (lecture).
        venture_id: Venture testée.

    Returns:
        True si un ticket HYPOTHESIS APPROVED niveau full existe.
    """
    row = conn.execute(
        "SELECT 1 FROM tickets WHERE type='HYPOTHESIS' AND state='APPROVED'"
        " AND json_extract(payload_json,'$.venture_id')=?"
        " AND json_extract(payload_json,'$.niveau')='full'",
        (venture_id,),
    ).fetchone()
    return row is not None


def create_venture(conn: sqlite3.Connection, name: str) -> str:
    """Crée une venture CANDIDATE (non schedulable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        name: Nom de la venture.

    Returns:
        L'id de la venture.
    """
    venture_id = _new_id()
    moment = utcnow()
    conn.execute(
        'INSERT INTO ventures(id, name, lifecycle, schedulable, created_at,'
        " updated_at) VALUES(?,?,'CANDIDATE',0,?,?)",
        (venture_id, name, moment, moment),
    )
    append_event(
        conn,
        actor='lifecycle',
        type='venture.candidate',
        venture_id=venture_id,
        payload={'name': name},
    )
    return venture_id


def to_smoke_ready(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(
        conn,
        venture_id,
        frozenset({'CANDIDATE', 'PIVOT', 'EXTEND', 'INVALID_RETRY'}),
        'SMOKE_READY',
    )


def to_smoke_running(conn: sqlite3.Connection, venture_id: str) -> None:
    if not _ready_campaign(conn, venture_id):
        raise VentureError(f'{venture_id} : campagne READY requise (smoke)')
    _move(conn, venture_id, frozenset({'SMOKE_READY'}), 'SMOKE_RUNNING')


def to_smoke_done(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(conn, venture_id, frozenset({'SMOKE_RUNNING'}), 'SMOKE_DONE')


def to_full_ready(conn: sqlite3.Connection, venture_id: str) -> None:
    if not approved_full_hypothesis(conn, venture_id):
        raise VentureError(f'{venture_id} : hypothèse full approuvée requise')
    if not collect_ready(conn, venture_id):
        raise VentureError(f'{venture_id} : collect READY requis (canary 1 €)')
    _move(
        conn,
        venture_id,
        frozenset({'SMOKE_DONE', 'PIVOT', 'EXTEND', 'INVALID_RETRY'}),
        'FULL_READY',
    )


def to_full_running(conn: sqlite3.Connection, venture_id: str) -> None:
    if not _ready_campaign(conn, venture_id):
        raise VentureError(f'{venture_id} : campagne READY requise (full)')
    _move(
        conn, venture_id, frozenset({'FULL_READY', 'EXTEND'}), 'FULL_RUNNING'
    )


def to_scale(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(
        conn,
        venture_id,
        frozenset({'SMOKE_DONE', 'FULL_RUNNING'}),
        'SCALE',
    )


def to_pivot(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(conn, venture_id, frozenset({'FULL_RUNNING'}), 'PIVOT')


def to_extend(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(conn, venture_id, frozenset({'FULL_RUNNING'}), 'EXTEND')


def to_killed(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(conn, venture_id, frozenset({'FULL_RUNNING'}), 'KILLED')


def to_invalid_retry(conn: sqlite3.Connection, venture_id: str) -> None:
    _move(
        conn,
        venture_id,
        frozenset({'SMOKE_RUNNING', 'FULL_RUNNING'}),
        'INVALID_RETRY',
    )
