#!/usr/bin/env python3
"""Migration v53 : les campagnes, le couloir d'essai, repartir d'une tâche
(lot 12, décisions Q98 et Q99).

Le couloir d'essai :
- ``tasks.trial_run`` : l'essai dont une tâche fait partie (vide : le vrai
  pipeline) ; ``tasks.parent_id`` : la tâche qui l'a créée ;
  ``tasks.rerun`` : la marque d'un redémarrage (« Repartir d'ici ») ;
- ``trial`` sur les cycles d'écoute, les pages, les tickets, leurs
  réponses et les choix du principal : 1 pour ce qu'un essai a écrit ;
- ``tickets.task_id`` : la tâche qui a ouvert le ticket ;
- ``invocation_settings.trial_value`` : la valeur d'un réglage dans un
  essai (vide : la même) ;
- ``links.lane`` et ``triggers.lane`` : vide (les deux couloirs), ``real``
  ou ``trial`` ; ``link_passages.from_task`` : la tâche d'où vient un
  passage ;
- ``trigger_row_conditions`` : un déclencheur ne part que si un nombre de
  lignes est atteint, ou pas dépassé.

Les campagnes :
- ``campaigns.family`` devient ``phase`` (``smoke`` ou ``full``), partout
  où la base nomme cette colonne ; la campagne reçoit sa cible, son angle,
  son volume par semaine, son début, sa fin prévue, la raison de sa fin et
  le compte de ses recherches de prospects restées vides ;
- ``contact_addresses.source_url`` : la page où l'adresse a été trouvée ;
  ``contacts.note`` : qui est ce prospect, et pourquoi il est visé ;
- ``test_reports`` : le compte rendu d'un test léger ;
- ``principal_choices`` : une proposition de business principal.
"""

from __future__ import annotations

import sqlite3

_AJOUTS = (
    ('tasks', 'trial_run', "TEXT NOT NULL DEFAULT ''"),
    ('tasks', 'parent_id', "TEXT NOT NULL DEFAULT ''"),
    ('tasks', 'rerun', "TEXT NOT NULL DEFAULT ''"),
    ('listen_cycles', 'trial', 'INTEGER NOT NULL DEFAULT 0'),
    ('listen_docs', 'trial', 'INTEGER NOT NULL DEFAULT 0'),
    ('tickets', 'trial', 'INTEGER NOT NULL DEFAULT 0'),
    ('tickets', 'task_id', "TEXT NOT NULL DEFAULT ''"),
    ('ticket_answers', 'trial', 'INTEGER NOT NULL DEFAULT 0'),
    ('invocation_settings', 'trial_value', "TEXT NOT NULL DEFAULT ''"),
    ('links', 'lane', "TEXT NOT NULL DEFAULT ''"),
    ('triggers', 'lane', "TEXT NOT NULL DEFAULT ''"),
    ('link_passages', 'from_task', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'target', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'angle', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'n_week', 'INTEGER NOT NULL DEFAULT 0'),
    ('campaigns', 'started_at', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'planned_end_at', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'end_reason', "TEXT NOT NULL DEFAULT ''"),
    ('campaigns', 'dry_searches', 'INTEGER NOT NULL DEFAULT 0'),
    ('campaigns', 'found_at_search', 'INTEGER NOT NULL DEFAULT -1'),
    ('contact_addresses', 'source_url', "TEXT NOT NULL DEFAULT ''"),
    ('contacts', 'note', "TEXT NOT NULL DEFAULT ''"),
)
# Les tables de la base qui nomment une colonne des campagnes.
_NOMMENT = (
    ('writable_columns', 'table_name', 'column_name'),
    ('table_view_columns', 'table_name', 'column_name'),
    ('tool_db_columns', 'table_name', 'column_name'),
    ('status_transitions', 'table_name', 'column_name'),
)


def _colonnes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    }


def _existe(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is not None
    )


def _phase(connection: sqlite3.Connection) -> None:
    """``campaigns.family`` devient ``phase``, partout où elle est nommée."""
    if 'family' not in _colonnes(connection, 'campaigns'):
        return
    connection.execute('ALTER TABLE campaigns RENAME COLUMN family TO phase')
    connection.execute("UPDATE campaigns SET phase='smoke'")
    for table, ou, colonne in _NOMMENT:
        if _existe(connection, table):
            connection.execute(
                f"UPDATE OR IGNORE {table} SET {colonne}='phase'"
                f" WHERE {ou}='campaigns' AND {colonne}='family'"
            )
    if _existe(connection, 'invocation_write_values'):
        connection.execute(
            "UPDATE invocation_write_values SET column_name='phase',"
            " value='smoke' WHERE column_name='family' AND write_id IN"
            " (SELECT id FROM invocation_writes WHERE table_name='campaigns')"
        )


def apply_v053(connection: sqlite3.Connection) -> None:
    """Ajoute les colonnes et les tables du lot 12."""
    for table, colonne, sorte in _AJOUTS:
        if colonne not in _colonnes(connection, table):
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN {colonne} {sorte}'
            )
    _phase(connection)
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS trigger_row_conditions (
            trigger_id TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            counted_values TEXT NOT NULL,
            op TEXT NOT NULL CHECK (op IN ('at_most', 'at_least')),
            n INTEGER NOT NULL CHECK (n >= 0),
            description TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (trigger_id, position)
        );
        CREATE TABLE IF NOT EXISTS test_reports (
            id TEXT PRIMARY KEY,
            venture_id TEXT NOT NULL,
            contacted INTEGER NOT NULL DEFAULT 0,
            replies INTEGER NOT NULL DEFAULT 0,
            points REAL NOT NULL DEFAULT 0,
            spend_eur REAL NOT NULL DEFAULT 0,
            points_per_eur REAL,
            figures TEXT NOT NULL DEFAULT '',
            verdict TEXT NOT NULL DEFAULT ''
                CHECK (verdict IN ('', 'retenu', 'non_retenu')),
            verdict_reason TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_test_reports_venture
            ON test_reports(venture_id);
        CREATE TABLE IF NOT EXISTS principal_choices (
            id TEXT PRIMARY KEY,
            proposed_venture_id TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'PROPOSED'
                CHECK (status IN ('PROPOSED', 'DECIDED')),
            decision TEXT NOT NULL DEFAULT '',
            chosen_venture_id TEXT NOT NULL DEFAULT '',
            trial INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_trial_run ON tasks(trial_run);
        CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
        """
    )
