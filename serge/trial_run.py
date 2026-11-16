#!/usr/bin/env python3
"""Démarrer et arrêter un essai (décision Q99).

Un seul essai à la fois : son numéro est dans ``runtime_flags``, c'est
celui de la tâche qui l'a lancé. Arrêter un essai (le relancer, ou le
bouton « Arrêter l'essai ») :

- annule ses tâches en attente, et ferme ses tickets ouverts ;
- abandonne son cycle d'écoute, annule ses campagnes et ses envois qui
  n'étaient pas partis ;
- passe à « arrêté » (``KILLED``) son business, s'il n'était pas arrivé au
  bout : les conditions de la suite (« plus aucun test ne tourne ») ne
  restent pas bloquées par un vieil essai.

Une tâche d'essai en cours finit ; sa suite ne part pas
(``serge/interpreter/flow.py``). Ce qui est en ligne (un site, des
produits dans Stripe) reste.
"""

from __future__ import annotations

import sqlite3

from serge.db.store import append_event, utcnow
from serge.tickets.lifecycle import OPENISH, cancel
from serge.trial import FLAG, active_run

# Un business d'essai arrivé à l'un de ces statuts est allé au bout.
FINISHED = ('KILLED', 'PRODUCT_READY', 'FULL_RUNNING')
_TRIAL_VENTURES = 'SELECT id FROM ventures WHERE trial=1'


def begin_trial(conn: sqlite3.Connection, run_id: str) -> None:
    """Note l'essai qui démarre : ``run_id`` est la tâche qui le lance."""
    conn.execute(
        'INSERT OR REPLACE INTO runtime_flags(name, value, set_by, set_at)'
        ' VALUES(?,?,?,?)',
        (FLAG, run_id, 'owner', utcnow()),
    )
    append_event(
        conn, actor='owner', type='trial.started', payload={'run': run_id}
    )


def stop_trial(conn: sqlite3.Connection, reason: str) -> dict[str, int]:
    """Arrête tout ce qui reste d'un essai. Rend ce qui a été arrêté.

    Sans essai en cours et sans rien à arrêter, ne fait rien.
    """
    now = utcnow()
    run = active_run(conn)
    tasks = conn.execute(
        "UPDATE tasks SET status='cancelled', finished_at=?, last_error=?"
        " WHERE trial_run<>'' AND status IN ('ready', 'blocked')",
        (now, f'essai arrêté : {reason}'),
    ).rowcount
    holes = ','.join('?' * len(OPENISH))
    tickets = [
        str(r[0])
        for r in conn.execute(
            f'SELECT id FROM tickets WHERE trial=1 AND state IN ({holes})',
            sorted(OPENISH),
        ).fetchall()
    ]
    for ticket_id in tickets:
        cancel(conn, ticket_id, f'essai arrêté : {reason}')
    conn.execute(
        "UPDATE listen_cycles SET status='ABANDONED', finished_at=?"
        " WHERE trial=1 AND status='OPEN'",
        (now,),
    )
    conn.execute(
        "UPDATE campaigns SET state='CANCELLED', end_reason=?, updated_at=?"
        " WHERE state IN ('DRAFT', 'READY', 'RUNNING')"
        f' AND venture_id IN ({_TRIAL_VENTURES})',
        (f'essai arrêté : {reason}', now),
    )
    conn.execute(
        "UPDATE touches SET status='cancelled', last_error=?, updated_at=?"
        " WHERE status IN ('to_write', 'pending', 'waiting_owner')"
        f' AND venture_id IN ({_TRIAL_VENTURES})',
        (f'essai arrêté : {reason}', now),
    )
    ventures = conn.execute(
        "UPDATE ventures SET lifecycle='KILLED', updated_at=? WHERE trial=1"
        f' AND lifecycle NOT IN ({",".join("?" * len(FINISHED))})',
        (now, *FINISHED),
    ).rowcount
    conn.execute('DELETE FROM runtime_flags WHERE name=?', (FLAG,))
    done = {'tasks': tasks, 'tickets': len(tickets), 'ventures': ventures}
    if run or any(done.values()):
        append_event(
            conn,
            actor='owner',
            type='trial.stopped',
            payload={'run': run, 'reason': reason, **done},
        )
    return done
