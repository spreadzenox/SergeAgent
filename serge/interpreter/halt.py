#!/usr/bin/env python3
"""Arrêter une tâche en plein travail.

Trois raisons, vérifiées avant chaque appel au modèle et avant chaque
outil :

- **le coupe-circuit** : Serge a été arrêté dans Mission Control. La tâche
  s'arrête tout de suite, sans écrire sa réponse, et repart du début quand
  Serge redémarre. Un appel au modèle ou une commande déjà partis ne
  s'interrompent pas d'eux-mêmes : le chien de garde de la file
  (``watchdog``) arrête alors son programme, que systemd relance ;
- **le plafond de dépense d'une tâche** (page Policy, « Dépense maximale
  d'une tâche »), pour sa tentative en cours : exemple, une construction
  qui a coûté 5,02 € pour un plafond de 5 € s'arrête en échec, avec la
  raison, et Julien et Clem en sont prévenus ;
- **une demande à Julien** : l'invocation a appelé « Demander une nouvelle
  capacité » ; la tâche est gelée jusqu'à sa réponse (voir
  ``serge/demande_capacite.py``).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time
from collections.abc import Callable
from pathlib import Path

from serge.coupe_circuit import heartbeat_marche
from serge.policy_store import policy_en_vigueur


class TaskCut(RuntimeError):
    """Serge a été arrêté par le coupe-circuit pendant la tâche."""


class TaskOverBudget(RuntimeError):
    """La tâche a dépensé son plafond."""


class TaskFrozen(RuntimeError):
    """La tâche attend la réponse de Julien à une demande (un ticket)."""

    def __init__(self, ticket_id: str) -> None:
        super().__init__(f'en attente de Julien : ticket {ticket_id}')
        self.ticket_id = ticket_id


def task_spend_eur(conn: sqlite3.Connection, task_id: str) -> float:
    """Ce que la tentative en cours d'une tâche a coûté en appels au modèle,
    en euros : depuis son dernier départ (``tasks.started_at``).

    Une tâche qui repart du début (coupée, sans crédit, dégelée, relancée)
    a de nouveau tout son plafond : le 15 novembre 2026, une relecture
    reprise après une panne d'OpenRouter s'arrêtait à cause des 4,5 € de
    la tentative perdue.
    """
    policy = policy_en_vigueur(conn)
    taux = float((policy.get('budget') or {}).get('eur_per_usd', 0) or 0)
    row = conn.execute(
        'SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE task_id=?'
        ' AND created_at >= COALESCE((SELECT started_at FROM tasks'
        " WHERE id=?), '')",
        (task_id, task_id),
    ).fetchone()
    return float(row[0]) * taux


def check_halt(conn: sqlite3.Connection, task_id: str) -> None:
    """Lève l'arrêt dû, s'il y en a un.

    Raises:
        TaskCut: Serge est arrêté.
        TaskOverBudget: La tâche a dépensé son plafond (0 : pas de plafond).
    """
    if not heartbeat_marche(conn):
        raise TaskCut('Serge arrêté par le coupe-circuit')
    if not task_id:
        return
    plafond = float(
        (policy_en_vigueur(conn).get('budget') or {}).get('task_max_eur', 0)
        or 0
    )
    if plafond <= 0:
        return
    depense = task_spend_eur(conn, task_id)
    if depense >= plafond:
        raise TaskOverBudget(
            f'plafond de dépense de la tâche atteint : {depense:.2f} €'
            f' pour {plafond:.2f} € permis (page Policy, « Dépense maximale'
            ' d’une tâche »)'
        )


# Le temps laissé à une tâche pour s'arrêter d'elle-même après le
# coupe-circuit (le temps d'un appel au modèle), avant que le chien de
# garde arrête la file.
GRACE_S = 45


def watchdog(
    path: Path,
    running: Callable[[], str],
    *,
    every_s: float = 2.0,
    grace_s: float = GRACE_S,
    stop: Callable[[int], None] = os._exit,
) -> threading.Thread:
    """Le chien de garde d'une file : arrête son programme si une tâche
    tourne encore ``grace_s`` secondes après le coupe-circuit.

    Il lit la base par sa propre connexion, en lecture seule. systemd
    relance la file, qui remet la tâche coupée dans la file sans la lancer
    tant que Serge est arrêté.

    Args:
        path: La base.
        running: Rend la tâche en cours, ou ``''``.
        every_s: Tous les combien il regarde.
        grace_s: Le délai avant d'arrêter le programme.
        stop: Ce qui arrête le programme (un code de sortie non nul).
    """

    def garder() -> None:
        coupe_depuis = 0.0
        while True:
            time.sleep(every_s)
            try:
                conn = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
                try:
                    marche = heartbeat_marche(conn)
                finally:
                    conn.close()
            except sqlite3.Error:
                continue
            tache = running()
            if marche or not tache:
                coupe_depuis = 0.0
                continue
            coupe_depuis = coupe_depuis or time.monotonic()
            if time.monotonic() - coupe_depuis >= grace_s:
                print(
                    f'coupe-circuit : la tâche {tache} ne s’arrête pas,'
                    ' la file s’arrête',
                    flush=True,
                )
                stop(3)
                return

    thread = threading.Thread(target=garder, daemon=True)
    thread.start()
    return thread
