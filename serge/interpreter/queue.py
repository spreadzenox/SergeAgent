#!/usr/bin/env python3
"""Vider une file, une tâche après l'autre.

Chaque file (``conversations``, ``works``) a son propre programme, qui
tourne en continu. À chaque tour, il lance les déclencheurs horaires dus,
prend la tâche prête la plus prioritaire de sa file, l'exécute et
enregistre en base. Si la tâche échoue, ses écritures sont annulées et
elle est marquée en échec, avec la raison ; la file continue.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from serge.coupe_circuit import heartbeat_marche
from serge.db.store import utcnow
from serge.interpreter.flow import fire_due_triggers
from serge.interpreter.prompt import Caller
from serge.interpreter.run import fail_task, run_task
from serge.interpreter.tasks import next_task


def _queue_enabled(conn: sqlite3.Connection, queue_id: str) -> bool:
    row = conn.execute(
        'SELECT enabled FROM queues WHERE id=?', (queue_id,)
    ).fetchone()
    return bool(row and int(row[0]))


def process_one(
    conn: sqlite3.Connection,
    queue_id: str,
    *,
    now: str | None = None,
    caller: Caller | None = None,
    root: Path | None = None,
    timezone: str = 'Europe/Paris',
) -> str | None:
    """Traite au plus une tâche de la file. Rend son id, ou ``None``."""
    moment = now or utcnow()
    fire_due_triggers(conn, moment, timezone)
    conn.commit()
    if not heartbeat_marche(conn, moment) or not _queue_enabled(
        conn, queue_id
    ):
        return None
    task_id = next_task(conn, queue_id, moment)
    if task_id is None:
        return None
    try:
        run_task(conn, task_id, caller=caller, root=root)
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — une tâche en échec ne tue pas la file
        conn.rollback()
        fail_task(conn, task_id, f'{type(exc).__name__}: {exc}')
        conn.commit()
    return task_id


def run_forever(
    conn: sqlite3.Connection,
    queue_id: str,
    *,
    idle_seconds: float = 2.0,
    timezone: str = 'Europe/Paris',
) -> None:
    """Vide la file sans fin ; attend un peu quand il n'y a rien à faire."""
    while True:
        if process_one(conn, queue_id, timezone=timezone) is None:
            time.sleep(idle_seconds)
