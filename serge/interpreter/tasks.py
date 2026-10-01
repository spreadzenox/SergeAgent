#!/usr/bin/env python3
"""La file des tâches : une tâche lance une invocation avec ses paramètres.

Chaque file (``conversations``, ``works``) est vidée par son propre
programme, une tâche après l'autre, la plus prioritaire d'abord.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db.store import utcnow


class TaskError(ValueError):
    """Une tâche ne peut pas être créée."""


def task_key(
    invocation_id: str, origin: str, origin_ref: str, params: Mapping[str, Any]
) -> str:
    """Clé stable d'une tâche : la même demande donne toujours la même clé.

    Exemple : le lien ``l1`` qui passe la ligne ``v_3`` produit toujours la
    même clé, même après un redémarrage ; la tâche n'est donc jamais créée
    deux fois.
    """
    blob = json.dumps(
        [invocation_id, origin, origin_ref, sorted(params.items())],
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(blob.encode('utf-8')).hexdigest()[:32]


def enqueue_task(
    conn: sqlite3.Connection,
    invocation_id: str,
    params: Mapping[str, Any] | None = None,
    *,
    origin: str = '',
    origin_ref: str = '',
    not_before: str = '',
    key: str = '',
) -> str | None:
    """Ajoute une tâche à la file de son invocation.

    La file et la priorité sont lues sur l'invocation au moment de la
    création. Une invocation éteinte ou supprimée ne reçoit pas de tâche.

    Returns:
        L'id de la tâche, celui de la tâche déjà existante pour la même
        clé, ou ``None`` si l'invocation ne peut pas être lancée.

    Raises:
        TaskError: Invocation inconnue.
    """
    row = conn.execute(
        'SELECT queue_id, priority, enabled, deleted_at FROM invocations'
        ' WHERE id=?',
        (invocation_id,),
    ).fetchone()
    if row is None:
        raise TaskError(f'invocation inconnue : {invocation_id}')
    if not int(row[2]) or str(row[3] or ''):
        return None
    values = {
        str(k): '' if v is None else str(v) for k, v in (params or {}).items()
    }
    idem = key or task_key(invocation_id, origin, origin_ref, values)
    found = conn.execute(
        'SELECT id FROM tasks WHERE idempotency_key=?', (idem,)
    ).fetchone()
    if found is not None:
        return str(found[0])
    task_id = f't_{idem[:20]}'
    conn.execute(
        'INSERT INTO tasks(id, invocation_id, queue_id, priority, status,'
        ' not_before, origin, origin_ref, idempotency_key, created_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?,?)',
        (
            task_id,
            invocation_id,
            str(row[0]),
            int(row[1]),
            'ready',
            not_before,
            origin,
            origin_ref,
            idem,
            utcnow(),
        ),
    )
    for name, value in values.items():
        conn.execute(
            'INSERT INTO task_params(task_id, name, value) VALUES(?,?,?)',
            (task_id, name, value),
        )
    return task_id


def task_params(conn: sqlite3.Connection, task_id: str) -> dict[str, str]:
    """Les paramètres d'une tâche."""
    return {
        str(name): str(value)
        for name, value in conn.execute(
            'SELECT name, value FROM task_params WHERE task_id=?', (task_id,)
        ).fetchall()
    }


def next_task(
    conn: sqlite3.Connection, queue_id: str, now: str, *, llm: bool = True
) -> str | None:
    """La tâche prête la plus prioritaire de cette file, ou ``None``.

    Une tâche est prête si sa date « pas avant » est passée, si son
    invocation est allumée, et si l'étape de l'invocation n'est pas coupée.
    Avec ``llm`` faux (plafond de dépense du jour atteint), les tâches des
    invocations LLM attendent le lendemain.
    """
    no_llm = '' if llm else " AND i.type<>'llm'"
    row = conn.execute(
        'SELECT t.id FROM tasks t'
        ' JOIN invocations i ON i.id=t.invocation_id'
        ' LEFT JOIN pipeline_steps s ON s.id=i.step_id'
        " WHERE t.queue_id=? AND t.status='ready'"
        " AND (t.not_before='' OR t.not_before<=?)"
        " AND i.enabled=1 AND i.deleted_at=''"
        f' AND COALESCE(s.enabled, 1)=1{no_llm}'
        ' ORDER BY t.priority DESC, t.created_at, t.id LIMIT 1',
        (queue_id, now),
    ).fetchone()
    return str(row[0]) if row else None


def start_task(conn: sqlite3.Connection, task_id: str) -> bool:
    """Passe une tâche prête en cours. Faux si elle ne l'était plus."""
    cursor = conn.execute(
        "UPDATE tasks SET status='running', started_at=?,"
        " attempts=attempts+1 WHERE id=? AND status='ready'",
        (utcnow(), task_id),
    )
    return cursor.rowcount == 1


def finish_task(
    conn: sqlite3.Connection, task_id: str, *, error: str = ''
) -> None:
    """Termine une tâche : ``done``, ou ``failed`` avec la raison."""
    conn.execute(
        'UPDATE tasks SET status=?, last_error=?, finished_at=? WHERE id=?',
        ('failed' if error else 'done', error[:500], utcnow(), task_id),
    )


def relaunch_task(conn: sqlite3.Connection, task_id: str) -> bool:
    """Remet une tâche échouée dans sa file. Faux si elle n'avait pas échoué.

    Elle repart de zéro ; son nombre d'essais est gardé.
    """
    cursor = conn.execute(
        "UPDATE tasks SET status='ready', last_error='', not_before='',"
        " started_at='', finished_at='' WHERE id=? AND status='failed'",
        (task_id,),
    )
    return cursor.rowcount == 1


def cancel_task(conn: sqlite3.Connection, task_id: str, reason: str) -> bool:
    """Annule une tâche en attente. Faux si elle n'était pas en attente.

    Une tâche en cours ne s'annule pas : elle finit ce qu'elle a commencé.
    """
    from serge.horloge import iso_utc

    cursor = conn.execute(
        "UPDATE tasks SET status='cancelled', finished_at=?, last_error=?"
        " WHERE id=? AND status='ready'",
        (iso_utc(), reason, task_id),
    )
    return cursor.rowcount == 1
