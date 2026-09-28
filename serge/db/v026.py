#!/usr/bin/env python3
"""Migration v26 : les réglages des invocations et les quotas des tables.

- ``invocation_settings`` : les réglages d'une invocation, une ligne par
  réglage. Exemple : « nombre d'idées = 2 », entre 1 et 10. Un réglage
  marqué ``policy`` apparaît sur la page Policy de Mission Control.
- ``table_quotas`` : une protection de plus sur une table, « au plus N
  lignes dont telle colonne vaut l'une de ces valeurs ». Exemple : au plus
  3 business choisis pour un POC.
- ``invocation_output_fields`` gagne ``min_items`` et ``max_items`` (le
  nombre d'éléments d'une liste : un nombre, ou le nom d'un réglage), et
  ``invocation_writes`` gagne ``max_rows`` (au plus N lignes écrites).
- Une source de plus, ``setting`` (la valeur d'un réglage de
  l'invocation), dans les paramètres des outils et de la capacité, les
  valeurs écrites et les paramètres des liens. SQLite ne sait pas modifier
  une contrainte : ces trois tables sont recréées, avec leurs lignes.

Conception : ``docs/LOT6_CONCEPTION.md``, partie 17.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS invocation_settings (
    invocation_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'number'
        CHECK (type IN ('number', 'text', 'bool')),
    value TEXT NOT NULL DEFAULT '',
    min_value TEXT NOT NULL DEFAULT '',
    max_value TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    policy INTEGER NOT NULL DEFAULT 0 CHECK (policy IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (invocation_id, name)
);
CREATE TABLE IF NOT EXISTS table_quotas (
    id TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    counted_values TEXT NOT NULL,
    max_value INTEGER NOT NULL CHECK (max_value >= 0),
    description TEXT NOT NULL DEFAULT '',
    policy INTEGER NOT NULL DEFAULT 1 CHECK (policy IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);

CREATE TABLE invocation_tool_params_v26 (
    invocation_id TEXT NOT NULL,
    invocation_tool_id INTEGER NOT NULL DEFAULT 0,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('fixed', 'task', 'setting')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (invocation_id, invocation_tool_id, param_name)
);
INSERT INTO invocation_tool_params_v26 SELECT * FROM invocation_tool_params;
DROP TABLE invocation_tool_params;
ALTER TABLE invocation_tool_params_v26 RENAME TO invocation_tool_params;

CREATE TABLE invocation_write_values_v26 (
    write_id INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (
        source IN ('field', 'fixed', 'task', 'parent_row', 'now', 'setting')
    ),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (write_id, column_name)
);
INSERT INTO invocation_write_values_v26
    SELECT * FROM invocation_write_values;
DROP TABLE invocation_write_values;
ALTER TABLE invocation_write_values_v26 RENAME TO invocation_write_values;

CREATE TABLE link_params_v26 (
    link_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('row', 'task', 'fixed', 'setting')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (link_id, param_name)
);
INSERT INTO link_params_v26 SELECT * FROM link_params;
DROP TABLE link_params;
ALTER TABLE link_params_v26 RENAME TO link_params;
"""


def _add_column(
    conn: sqlite3.Connection, table: str, column: str, decl: str
) -> None:
    names = {str(r[1]) for r in conn.execute(f'PRAGMA table_info({table})')}
    if column not in names:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {decl}')


def apply_v026(connection: sqlite3.Connection) -> None:
    """Crée les réglages et les quotas, ajoute la source ``setting``."""
    connection.executescript(SCRIPT)
    for column in ('min_items', 'max_items'):
        _add_column(
            connection,
            'invocation_output_fields',
            column,
            "TEXT NOT NULL DEFAULT ''",
        )
    _add_column(
        connection, 'invocation_writes', 'max_rows', "TEXT NOT NULL DEFAULT ''"
    )
