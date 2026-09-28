#!/usr/bin/env python3
"""Migration v29 : l'étape 1 dans le pipeline en base (lot 7).

Les tables de l'étape 1 :

- ``listen_feeds`` (nouvelle) : les flux RSS que Serge a choisis. Une
  ligne par flux : adresse, titre, invocation qui l'a ajouté, actif ou
  non, dernière lecture.
- ``listen_docs`` : une page gardée. Elle gagne ``feed_id`` (le flux qui
  l'a ramenée), ``cycle_id`` (le cycle où elle a été triée), ``label``
  (son étiquette de tri : besoin nouveau, bruit, enrichit un business,
  preuve) et ``labelled_at``. L'aperçu est ``excerpt`` ; le texte entier
  n'est jamais gardé. ``cluster_id`` (l'ancien regroupement) disparaît,
  comme ``listen_cycle_docs`` : le cycle d'une page est sur la page.
- ``listen_cycles`` perd ``needs_target`` et ``business_target`` (plus
  utilisés) et gagne ``choice_note`` (ce que « Choisir » dit du cycle,
  par exemple pourquoi il n'a rien choisi).
- ``ventures`` gagne ``family`` (sa famille de business) et
  ``choice_reason`` (pourquoi il a été choisi).

Ce que l'interpréteur sait faire en plus :

- ``triggers.confirm_text`` : la question posée avant de lancer un
  bouton ; ``trigger_conditions`` : un déclencheur ne crée de tâche que
  si ces quotas ont de la place (exemple : il reste une place de test).
- ``invocation_tools.batch_size`` : une lecture d'office donnée par
  paquets, un appel au modèle par paquet ; ``max_calls`` : au plus N
  appels d'un outil par passage. Un nombre ou le nom d'un réglage.
- ``writable_tables.can_delete`` et l'opération ``delete`` des règles
  d'écriture (``invocation_writes`` est recréée pour sa contrainte).
- ``tool_db_filters`` accepte ``days_ago`` : « plus vieux que N jours »
  (recréée pour sa contrainte).

Le catalogue qui visait une colonne ou une table disparue est nettoyé.

Conception : ``docs/LOT7_CONCEPTION.md``.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS listen_feeds (
    id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    last_read_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS trigger_conditions (
    trigger_id TEXT NOT NULL,
    quota_id TEXT NOT NULL,
    PRIMARY KEY (trigger_id, quota_id)
);

CREATE TABLE invocation_writes_v29 (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invocation_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL
        CHECK (operation IN ('insert', 'update', 'delete')),
    for_each TEXT NOT NULL DEFAULT '',
    parent_write_id INTEGER NOT NULL DEFAULT 0,
    key_column TEXT NOT NULL DEFAULT '',
    key_source TEXT NOT NULL DEFAULT ''
        CHECK (key_source IN ('', 'field', 'fixed', 'task')),
    key_value TEXT NOT NULL DEFAULT '',
    max_rows TEXT NOT NULL DEFAULT ''
);
INSERT INTO invocation_writes_v29(id, invocation_id, position, table_name,
    operation, for_each, parent_write_id, key_column, key_source, key_value,
    max_rows)
    SELECT id, invocation_id, position, table_name, operation, for_each,
        parent_write_id, key_column, key_source, key_value, max_rows
    FROM invocation_writes;
DROP TABLE invocation_writes;
ALTER TABLE invocation_writes_v29 RENAME TO invocation_writes;
CREATE INDEX IF NOT EXISTS idx_invocation_writes_invocation
    ON invocation_writes(invocation_id, position);

CREATE TABLE tool_db_filters_v29 (
    tool_id TEXT NOT NULL,
    filter_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    operator TEXT NOT NULL DEFAULT '=',
    value_kind TEXT NOT NULL,
    value_text TEXT NOT NULL DEFAULT '',
    param_name TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tool_id, filter_id),
    CHECK (value_kind IN ('fixed', 'param', 'enum', 'days_ago')),
    CHECK (operator IN ('=', '!=', '<', '<=', '>', '>=', 'LIKE', 'IN'))
);
INSERT INTO tool_db_filters_v29 SELECT * FROM tool_db_filters;
DROP TABLE tool_db_filters;
ALTER TABLE tool_db_filters_v29 RENAME TO tool_db_filters;
"""

# Colonnes ajoutées : (table, colonne, déclaration).
_COLUMNS = (
    ('listen_docs', 'feed_id', "TEXT NOT NULL DEFAULT ''"),
    ('listen_docs', 'cycle_id', "TEXT NOT NULL DEFAULT ''"),
    (
        'listen_docs',
        'label',
        "TEXT NOT NULL DEFAULT '' CHECK (label IN ('', 'besoin_nouveau',"
        " 'bruit', 'enrichit', 'preuve'))",
    ),
    ('listen_docs', 'labelled_at', "TEXT NOT NULL DEFAULT ''"),
    ('listen_cycles', 'choice_note', "TEXT NOT NULL DEFAULT ''"),
    ('ventures', 'family', "TEXT NOT NULL DEFAULT ''"),
    ('ventures', 'choice_reason', "TEXT NOT NULL DEFAULT ''"),
    ('triggers', 'confirm_text', "TEXT NOT NULL DEFAULT ''"),
    ('invocation_tools', 'batch_size', "TEXT NOT NULL DEFAULT ''"),
    ('invocation_tools', 'max_calls', "TEXT NOT NULL DEFAULT ''"),
    (
        'writable_tables',
        'can_delete',
        'INTEGER NOT NULL DEFAULT 0 CHECK (can_delete IN (0, 1))',
    ),
)

# Colonnes retirées : (table, colonne).
_DROPPED = (
    ('listen_docs', 'cluster_id'),
    ('listen_cycles', 'needs_target'),
    ('listen_cycles', 'business_target'),
)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(r[1]) for r in conn.execute(f'PRAGMA table_info({table})')}


def _forget_column(conn: sqlite3.Connection, table: str, column: str) -> None:
    """Retire du catalogue tout ce qui visait une colonne disparue."""
    for catalogue in (
        'tool_db_columns',
        'writable_columns',
        'table_view_columns',
        'dedup_rule_columns',
    ):
        key = 'rule_id' if catalogue == 'dedup_rule_columns' else 'table_name'
        if catalogue == 'dedup_rule_columns':
            conn.execute(
                'DELETE FROM dedup_rule_columns WHERE column_name=? AND'
                ' rule_id IN (SELECT id FROM dedup_rules WHERE table_name=?)',
                (column, table),
            )
            continue
        conn.execute(
            f'DELETE FROM {catalogue} WHERE {key}=? AND column_name=?',
            (table, column),
        )
    conn.execute(
        'DELETE FROM invocation_write_values WHERE column_name=? AND write_id'
        ' IN (SELECT id FROM invocation_writes WHERE table_name=?)',
        (column, table),
    )


def _forget_table(conn: sqlite3.Connection, table: str) -> None:
    """Retire les outils de lecture qui lisaient une table disparue."""
    tools = [
        str(r[0])
        for r in conn.execute(
            'SELECT DISTINCT tool_id FROM tool_db_tables WHERE table_name=?',
            (table,),
        )
    ]
    for tool in tools:
        for catalogue in (
            'tool_db_tables',
            'tool_db_columns',
            'tool_db_filters',
            'tool_db_filter_values',
            'tool_db_joins',
            'tool_db_params',
            'tool_db_param_enums',
        ):
            conn.execute(f'DELETE FROM {catalogue} WHERE tool_id=?', (tool,))
        conn.execute(
            'DELETE FROM invocation_tool_params WHERE invocation_tool_id IN'
            ' (SELECT id FROM invocation_tools WHERE tool_id=?)',
            (tool,),
        )
        conn.execute('DELETE FROM invocation_tools WHERE tool_id=?', (tool,))
        conn.execute('DELETE FROM tools WHERE id=?', (tool,))


def apply_v029(connection: sqlite3.Connection) -> None:
    """Tables de l'étape 1, et ce que l'interpréteur sait faire en plus."""
    connection.executescript(SCRIPT)
    for table, column, decl in _COLUMNS:
        if column not in _columns(connection, table):
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN {column} {decl}'
            )
    if 'listen_cycle_docs' in {
        str(r[0])
        for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }:
        connection.execute(
            'UPDATE listen_docs SET cycle_id=(SELECT MIN(c.cycle_id) FROM'
            ' listen_cycle_docs c WHERE c.doc_id=listen_docs.id)'
            ' WHERE id IN (SELECT doc_id FROM listen_cycle_docs)'
        )
        _forget_table(connection, 'listen_cycle_docs')
        connection.execute('DROP TABLE listen_cycle_docs')
    for table, column in _DROPPED:
        if column in _columns(connection, table):
            _forget_column(connection, table, column)
            connection.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
