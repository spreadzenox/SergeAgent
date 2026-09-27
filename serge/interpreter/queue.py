#!/usr/bin/env python3
"""Vider une file, une tâche après l'autre.

Chaque file (``conversations``, ``works``) a son propre programme, qui
tourne en continu. À chaque tour, il lance les déclencheurs horaires dus,
prend la tâche prête la plus prioritaire de sa file, l'exécute et
enregistre en base. Si la tâche échoue, ses écritures sont annulées et
elle est marquée en échec, avec la raison ; la file continue. Quand le
plafond de dépense LLM du jour est atteint (réglé dans la policy), les
tâches LLM attendent le lendemain ; les autres continuent.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from serge.coupe_circuit import heartbeat_marche
from serge.db.store import append_event, utcnow
from serge.interpreter.flow import fire_due_triggers
from serge.interpreter.prompt import Caller
from serge.interpreter.run import fail_task, run_task
from serge.interpreter.tasks import next_task
from serge.llm.runtime import budget_spent
from serge.policy_snapshots import policy_en_vigueur
from serge.tickets import expire_due


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
    """Traite au plus une tâche de la file. Rend son id, ou ``None``.

    Quand Serge est arrêté en entier, les déclencheurs horaires ne créent
    pas de tâche : un arrêt d'une nuit ne laisse pas une pile de relèves
    de boîte mail à rattraper au redémarrage.
    """
    moment = now or utcnow()
    if not heartbeat_marche(conn, moment):
        return None
    fire_due_triggers(conn, moment, timezone)
    conn.commit()
    if not _queue_enabled(conn, queue_id):
        return None
    spent = budget_spent(conn, policy_en_vigueur(conn), moment[:10])
    conn.commit()
    task_id = next_task(conn, queue_id, moment, llm=not spent)
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


def resume_interrupted(conn: sqlite3.Connection, queue_id: str) -> list[str]:
    """Remet dans la file les tâches restées « en cours » à l'arrêt.

    Exemple : un déploiement redémarre la file pendant un appel au modèle.
    La tâche n'a rien écrit (ses écritures ne sont enregistrées qu'à la
    fin), elle est donc reprise depuis le début, et c'est noté au journal.
    Raccourci : valable tant qu'aucune capacité n'agit hors de Serge ; le
    lot 8 ajoute un état « à vérifier » pour celles qui envoient ou paient.

    Returns:
        Les tâches remises dans la file.
    """
    ids = [
        str(r[0])
        for r in conn.execute(
            "SELECT id FROM tasks WHERE queue_id=? AND status='running'",
            (queue_id,),
        ).fetchall()
    ]
    for task_id in ids:
        conn.execute(
            "UPDATE tasks SET status='ready', started_at='' WHERE id=?",
            (task_id,),
        )
        append_event(
            conn,
            actor=f'queue:{queue_id}',
            type='task.resumed',
            payload={'task': task_id},
        )
    conn.commit()
    return ids


def run_forever(
    conn: sqlite3.Connection,
    queue_id: str,
    *,
    idle_seconds: float = 2.0,
    timezone: str = 'Europe/Paris',
) -> None:
    """Vide la file sans fin ; attend un peu quand il n'y a rien à faire.

    Au démarrage, les tâches interrompues par l'arrêt précédent sont
    remises dans la file. À chaque tour, les tickets dont le délai est
    passé sont expirés : leur choix par défaut s'applique, même quand la
    file n'a rien à faire.
    """
    resume_interrupted(conn, queue_id)
    while True:
        expire_due(conn)
        conn.commit()
        if process_one(conn, queue_id, timezone=timezone) is None:
            time.sleep(idle_seconds)
