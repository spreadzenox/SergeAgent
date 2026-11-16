#!/usr/bin/env python3
"""Vider une file, une tâche après l'autre.

Chaque file (``conversations``, ``works``) a son propre programme, qui
tourne en continu. À chaque tour, il lance les déclencheurs horaires dus,
prend la tâche prête la plus prioritaire de sa file, l'exécute et
enregistre en base. Si la tâche échoue, ses écritures sont annulées et
elle est marquée en échec, avec la raison ; la file continue. Quand le
plafond de dépense LLM du jour est atteint (réglé dans la policy), les
tâches LLM attendent le lendemain ; les autres continuent.

Une tâche en plein travail s'arrête (``serge/interpreter/halt.py``) :
coupée par le coupe-circuit, elle revient dans la file et repartira du
début au redémarrage ; au-delà de son plafond de dépense, elle échoue et
Julien et Clem sont prévenus ; une demande à Julien la gèle jusqu'à sa
réponse. Sans crédit chez OpenRouter (ou chez Anthropic, appelé
directement), elle attend une demi-heure au lieu
d'échouer, et ils sont prévenus.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from serge.coupe_circuit import heartbeat_marche
from serge.db.store import append_event, utcnow
from serge.interpreter.halt import (
    TaskCut,
    TaskFrozen,
    TaskOverBudget,
    task_spend_eur,
    watchdog,
)
from serge.interpreter.prompt import Caller
from serge.interpreter.run import fail_task, run_task
from serge.interpreter.tasks import freeze_task, next_task
from serge.interpreter.triggers import fire_due_triggers
from serge.llm.runtime import budget_reached
from serge.policy_store import policy_en_vigueur
from serge.sandbox.navigateur import close_sessions
from serge.tickets import expire_due
from serge.tickets.reponses import noter_reponse
from serge.tickets.types import ticket_types

# La tâche en cours dans ce programme, pour le chien de garde.
EN_COURS = {'tache': ''}
# Sans crédit chez OpenRouter, une tâche LLM attend ce temps avant de
# réessayer.
ATTENTE_CREDIT = timedelta(minutes=30)


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
    spent = budget_reached(conn, policy_en_vigueur(conn), moment[:10])
    conn.commit()
    task_id = next_task(conn, queue_id, moment, llm=not spent)
    if task_id is None:
        return None
    EN_COURS['tache'] = task_id
    try:
        run_task(conn, task_id, caller=caller, root=root)
        conn.commit()
    except TaskCut:
        conn.rollback()
        _remettre(conn, task_id, 'task.cut', '')
    except TaskFrozen as exc:
        conn.rollback()
        freeze_task(conn, task_id, exc.ticket_id)
        _noter(conn, task_id, 'task.frozen', {'ticket': exc.ticket_id})
    except Exception as exc:  # noqa: BLE001 — une tâche en échec ne tue pas la file
        conn.rollback()
        raison = f'{type(exc).__name__}: {exc}'
        if raison.startswith('LlmError: CREDIT'):
            plus_tard = datetime.now(UTC) + ATTENTE_CREDIT
            _remettre(conn, task_id, 'task.no_credit', plus_tard.isoformat())
            fournisseur = (
                'Anthropic' if 'Anthropic' in raison else 'OpenRouter'
            )
            _prevenir(conn, f'{fournisseur} n’a plus de crédit', raison)
        else:
            fail_task(conn, task_id, raison)
            if isinstance(exc, TaskOverBudget):
                _prevenir(
                    conn,
                    'Une tâche a atteint son plafond de dépense',
                    f'{_titre(conn, task_id)} : {exc}',
                )
    finally:
        conn.commit()
        EN_COURS['tache'] = ''
        # Une session de navigateur ne survit pas à sa tâche.
        close_sessions()
    return task_id


def _noter(
    conn: sqlite3.Connection, task_id: str, kind: str, extra: dict
) -> None:
    row = conn.execute(
        'SELECT invocation_id FROM tasks WHERE id=?', (task_id,)
    ).fetchone()
    append_event(
        conn,
        actor=f'invocation:{row[0] if row else "?"}',
        type=kind,
        payload={
            'task': task_id,
            'spent_eur': round(task_spend_eur(conn, task_id), 4),
            **extra,
        },
    )


def _remettre(
    conn: sqlite3.Connection, task_id: str, kind: str, not_before: str
) -> None:
    """Remet une tâche arrêtée dans la file, sans rien écrire : elle
    repartira du début (après ``not_before``)."""
    conn.execute(
        "UPDATE tasks SET status='ready', started_at='', not_before=?"
        ' WHERE id=?',
        (not_before, task_id),
    )
    _noter(conn, task_id, kind, {'not_before': not_before})


def _titre(conn: sqlite3.Connection, task_id: str) -> str:
    row = conn.execute(
        'SELECT i.title FROM tasks t JOIN invocations i'
        ' ON i.id=t.invocation_id WHERE t.id=?',
        (task_id,),
    ).fetchone()
    return f'« {row[0]} »' if row else task_id


def _prevenir(conn: sqlite3.Connection, titre: str, texte: str) -> None:
    """Un ticket d'information pour Julien et Clem, sauf s'il y en a déjà
    un ouvert avec ce titre (une panne ne l'ouvre pas à chaque tâche)."""
    from serge.tickets.lifecycle import OPENISH, create_ticket, publish

    trous = ','.join('?' * len(OPENISH))
    if conn.execute(
        f"SELECT 1 FROM tickets WHERE type='FYI' AND title=?"
        f' AND state IN ({trous})',
        (titre, *sorted(OPENISH)),
    ).fetchone():
        return
    ticket_id = create_ticket(
        conn,
        ticket_types(conn),
        'FYI',
        titre,
        {'contenu': texte[:2000]},
        creator='serge',
    )
    publish(conn, ticket_id)


def resume_interrupted(conn: sqlite3.Connection, queue_id: str) -> list[str]:
    """Remet dans la file les tâches restées « en cours » à l'arrêt.

    Exemple : un déploiement redémarre la file pendant un appel au modèle.
    La tâche n'a rien écrit (ses écritures ne sont enregistrées qu'à la
    fin), elle est donc reprise depuis le début, et c'est noté au journal.
    Une capacité qui agit hors de Serge (envoyer un message) enregistre
    elle-même son état pendant la tâche : reprise, elle demande au canal si
    son envoi est parti avant de le refaire.

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


def expirer_tickets(
    conn: sqlite3.Connection, now: str | None = None
) -> list[str]:
    """Expire les tickets dépassés ; rend leurs ids.

    La décision par défaut d'un ticket expiré est une réponse : elle
    réveille les invocations réglées en base (décision Q85). Un type qui
    reste ouvert (une conversation qui attend Julien) n'est pas fermé.
    """
    faits = []
    for ticket_id, defaut in expire_due(conn, now, types=ticket_types(conn)):
        noter_reponse(conn, ticket_id, defaut, '', 'serge')
        faits.append(ticket_id)
    return faits


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
    from serge.db.store import default_canon_path

    watchdog(default_canon_path(), lambda: EN_COURS['tache'])
    while True:
        expirer_tickets(conn)
        conn.commit()
        if process_one(conn, queue_id, timezone=timezone) is None:
            time.sleep(idle_seconds)
