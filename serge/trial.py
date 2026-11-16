#!/usr/bin/env python3
"""Le couloir d'essai : ce qu'un essai lit, écrit et lance est à part.

Une tâche est soit du vrai pipeline, soit d'un essai (``tasks.trial_run``
porte le numéro de son essai). Pendant qu'elle tourne, ce fichier dit dans
quel couloir on est, et tout le reste suit, sans rien savoir d'une
invocation :

- une ligne écrite par une tâche d'essai est marquée (``trial`` à 1) dans
  les tables qui ont cette colonne ; les autres lignes suivent leur
  business, par leur ``venture_id`` ;
- une lecture ne rend que les lignes du couloir (``lane_clause``) ;
- une tâche créée pour une ligne est du couloir de cette ligne, sinon de
  la tâche qui l'a créée (``run_for_row``).

Exemple : « Choisir les business » ne voit jamais la calculatrice d'un
essai, et une page lue par l'essai n'est pas « déjà gardée » pour la
vraie écoute. Démarrer et arrêter un essai : ``serge/trial_run.py``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

# Le drapeau qui porte le numéro de l'essai en cours.
FLAG = 'essai_en_cours'
# Une tâche d'essai lancée hors de tout essai en cours. Exemple :
# « Supprimer de Stripe » sur la calculatrice d'un essai déjà arrêté.
NO_RUN = 'sans'

# La tâche que ce programme exécute : son essai (vide : le vrai pipeline)
# et son numéro. Chaque file tourne dans son propre programme, une tâche à
# la fois.
_STATE = {'run': '', 'task': ''}


def current_run() -> str:
    """L'essai de la tâche en cours, ou ``''`` (le vrai pipeline)."""
    return _STATE['run']


def current_task() -> str:
    """Le numéro de la tâche en cours, ou ``''``."""
    return _STATE['task']


def in_trial() -> bool:
    return bool(_STATE['run'])


@contextmanager
def lane(trial_run: str, task_id: str = '') -> Iterator[None]:
    """Le temps d'une tâche (ou d'un appel), on est dans son couloir."""
    before = dict(_STATE)
    _STATE.update(run=trial_run, task=task_id)
    try:
        yield
    finally:
        _STATE.update(before)


def active_run(conn: sqlite3.Connection) -> str:
    """Le numéro de l'essai en cours, ou ``''`` s'il n'y en a pas."""
    row = conn.execute(
        'SELECT value FROM runtime_flags WHERE name=?', (FLAG,)
    ).fetchone()
    return str(row[0]) if row else ''


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info("{table}")')}


def lane_clause(
    conn: sqlite3.Connection,
    table: str,
    alias: str = '',
    trial: bool | None = None,
) -> str:
    """La condition SQL qui ne garde que les lignes du couloir, ou ``''``.

    Une table qui a la colonne ``trial`` est filtrée dessus ; une table
    qui a ``venture_id`` suit son business ; les autres n'ont pas de
    couloir (les canaux, les réglages…). Exemple, dans le vrai pipeline :
    ``"ventures"."trial"=0``.
    """
    name = f'"{alias or table}"'
    columns = _columns(conn, table)
    essai = in_trial() if trial is None else trial
    if 'trial' in columns:
        return f'{name}."trial"={int(essai)}'
    if 'venture_id' in columns:
        word = 'IN' if essai else 'NOT IN'
        return (
            f'{name}."venture_id" {word}'
            ' (SELECT id FROM ventures WHERE trial=1)'
        )
    return ''


def row_in_trial(
    conn: sqlite3.Connection, row: Mapping[str, Any]
) -> bool | None:
    """Cette ligne est-elle d'un essai ? ``None`` : elle ne le dit pas."""
    if row.get('trial') is not None:
        return bool(int(row['trial'] or 0))
    venture = str(row.get('venture_id') or '')
    if not venture:
        return None
    found = conn.execute(
        'SELECT trial FROM ventures WHERE id=?', (venture,)
    ).fetchone()
    return bool(int(found[0])) if found else None


def run_for_row(
    conn: sqlite3.Connection, row: Mapping[str, Any], inherited: str
) -> str:
    """L'essai d'une tâche créée pour cette ligne (``''`` : le vrai).

    La ligne décide si elle le dit (un e-mail reçu d'un contact d'essai
    lance une tâche d'essai, même relevé par une vraie tâche) ; sinon la
    tâche hérite du couloir de celle qui l'a créée.
    """
    essai = row_in_trial(conn, row)
    if essai is None:
        return inherited
    if not essai:
        return ''
    return inherited or active_run(conn) or NO_RUN


def mark(
    conn: sqlite3.Connection, table: str, values: Mapping[str, Any]
) -> dict[str, Any]:
    """Les valeurs d'une ligne nouvelle, marquée si on est dans un essai."""
    if in_trial() and 'trial' in _columns(conn, table):
        return {**values, 'trial': 1}
    return dict(values)
