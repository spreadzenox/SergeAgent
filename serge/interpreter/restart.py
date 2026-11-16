#!/usr/bin/env python3
"""Repartir d'une tâche (décision Q99).

Une chaîne qui a bloqué repart d'une tâche précise, quel que soit son
état (finie, en échec, annulée, gelée), sauf en cours :

1. ce qui restait de l'ancienne chaîne est arrêté : les tâches en attente
   que cette tâche avait créées, et celles qu'elles avaient créées
   (``tasks.parent_id``), avec leurs tickets ouverts ;
2. une tâche neuve part, copie de l'ancienne : même invocation, mêmes
   paramètres, même couloir ;
3. elle porte une marque de redémarrage (``tasks.rerun``), que toute sa
   suite hérite : la marque entre dans la clé de chaque tâche et de chaque
   passage, donc un lien déjà passé pour l'ancienne chaîne passe de
   nouveau.

Exemple : le paiement test a fini sur « pas payé ». « Repartir d'ici »
refait le paiement, puis « Produit en vente », sans toucher au reste.
"""

from __future__ import annotations

import sqlite3
import uuid

from serge.db.store import append_event, utcnow
from serge.interpreter.tasks import REPONSES, enqueue_task, task_params
from serge.tickets.lifecycle import OPENISH, cancel
from serge.trial import NO_RUN, active_run


class RestartError(ValueError):
    """Cette tâche ne peut pas repartir ; le message dit pourquoi."""


def descendants(conn: sqlite3.Connection, task_id: str) -> list[str]:
    """La tâche et toutes celles qu'elle a créées, de proche en proche."""
    return [
        str(r[0])
        for r in conn.execute(
            'WITH RECURSIVE suite(id) AS ('
            ' SELECT ? UNION'
            ' SELECT t.id FROM tasks t JOIN suite s ON t.parent_id=s.id)'
            ' SELECT id FROM suite',
            (task_id,),
        ).fetchall()
    ]


def restart_from(conn: sqlite3.Connection, task_id: str) -> str:
    """Fait repartir la chaîne d'une tâche. Rend la tâche neuve.

    Raises:
        RestartError: Tâche inconnue ou en cours, essai remplacé, ou
            invocation éteinte.
    """
    row = conn.execute(
        'SELECT invocation_id, status, trial_run, parent_id FROM tasks'
        ' WHERE id=?',
        (task_id,),
    ).fetchone()
    if row is None:
        raise RestartError('tâche inconnue')
    invocation, status, trial_run, parent = (str(x or '') for x in row)
    if status == 'running':
        raise RestartError(
            'la tâche est en cours : attends qu’elle finisse, ou arrête-la'
        )
    if trial_run not in ('', NO_RUN) and trial_run != active_run(conn):
        raise RestartError(
            'cette tâche est d’un essai arrêté ou remplacé : relance l’essai'
        )
    now = utcnow()
    chain = descendants(conn, task_id)
    holes = ','.join('?' * len(chain))
    stopped = conn.execute(
        "UPDATE tasks SET status='cancelled', finished_at=?, last_error=?"
        f" WHERE id IN ({holes}) AND status IN ('ready', 'blocked')",
        (now, f'chaîne repartie de la tâche {task_id}', *chain),
    ).rowcount
    for (ticket_id,) in conn.execute(
        f'SELECT id FROM tickets WHERE task_id IN ({holes})'
        f' AND state IN ({",".join("?" * len(OPENISH))})',
        (*chain, *sorted(OPENISH)),
    ).fetchall():
        cancel(conn, str(ticket_id), f'chaîne repartie de la tâche {task_id}')
    # Les réponses de Julien à l'ancienne tâche ne valent pas pour la neuve.
    params = {
        k: v for k, v in task_params(conn, task_id).items() if k != REPONSES
    }
    mark = uuid.uuid4().hex[:8]
    new_id = enqueue_task(
        conn,
        invocation,
        params,
        origin_ref=f'reparti:{task_id}',
        trial_run=trial_run,
        parent=parent,
        rerun=mark,
    )
    if new_id is None:
        raise RestartError('son invocation est éteinte ou supprimée')
    append_event(
        conn,
        actor='owner',
        type='task.restarted',
        payload={'task': new_id, 'from': task_id, 'stopped': stopped},
    )
    return new_id
