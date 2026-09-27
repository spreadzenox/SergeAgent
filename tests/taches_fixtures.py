#!/usr/bin/env python3
"""Aide de test : des invocations sans LLM et des tâches, posées en base.

Les tests de Mission Control ont besoin de tâches dans les files (en
cours, prêtes, en échec). On les crée comme en production : des
invocations décrites en base (``seed_pipeline``), puis des tâches mises en
file par ``enqueue_task``.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.interpreter.tasks import enqueue_task, finish_task, start_task
from serge.pipeline_seed import seed_pipeline


def invocations(
    conn: sqlite3.Connection, *specs: tuple[str, str, str]
) -> None:
    """Pose des invocations sans LLM : ``(id, titre, étape)``."""
    seed_pipeline(
        conn,
        {
            'schema_version': 1,
            'invocations': [
                {
                    'id': ident,
                    'title': titre,
                    'role': f'{titre}. Invocation de test.',
                    'type': 'capability',
                    'capability': 'echo',
                    'step': etape,
                }
                for ident, titre, etape in specs
            ],
        },
    )


def tache(
    conn: sqlite3.Connection,
    invocation_id: str,
    params: dict[str, Any] | None = None,
    *,
    key: str,
    status: str = 'ready',
    created_at: str = '',
    not_before: str = '',
    error: str = '',
) -> str:
    """Met une tâche en file, puis la place dans l'état voulu.

    ``status`` : ``ready``, ``running``, ``done`` ou ``failed``.
    """
    task_id = enqueue_task(
        conn, invocation_id, params or {}, key=key, not_before=not_before
    )
    assert task_id is not None
    if status != 'ready':
        start_task(conn, task_id)
    if status in ('done', 'failed'):
        finish_task(
            conn,
            task_id,
            error=error or ('échec' if status == 'failed' else ''),
        )
    if created_at:
        conn.execute(
            'UPDATE tasks SET created_at=?, started_at=CASE started_at'
            " WHEN '' THEN '' ELSE ? END WHERE id=?",
            (created_at, created_at, task_id),
        )
    return task_id
