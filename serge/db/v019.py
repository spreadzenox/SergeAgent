#!/usr/bin/env python3
"""Migration v19 : catalogue DB des tools et capsules mémoire."""

from __future__ import annotations

import sqlite3


def _add_column(
    connection: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    columns = {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info({table})')
    }
    if column not in columns:
        connection.execute(
            f'ALTER TABLE {table} ADD COLUMN {column} {definition}'
        )


def apply_v019(connection: sqlite3.Connection) -> None:
    """Ajoute les permissions structurées et enrichit ``db_readers``.

    Les liens restent souples, comme dans le reste du canon : aucune clé
    étrangère n'est créée par cette migration.
    """
    _add_column(
        connection, 'db_readers', 'description', "TEXT NOT NULL DEFAULT ''"
    )
    _add_column(
        connection, 'db_readers', 'prompt_addition', "TEXT NOT NULL DEFAULT ''"
    )
    _add_column(
        connection, 'db_readers', 'tool_id', "TEXT NOT NULL DEFAULT ''"
    )
    connection.execute(
        "UPDATE db_readers SET description=doc_md WHERE description=''"
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tool_db_tables (
            tool_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tool_id, table_name)
        );
        CREATE TABLE IF NOT EXISTS tool_db_columns (
            tool_id TEXT NOT NULL,
            table_name TEXT NOT NULL,
            column_name TEXT NOT NULL,
            output_name TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tool_id, table_name, column_name)
        );
        CREATE TABLE IF NOT EXISTS tool_db_filters (
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
            CHECK (value_kind IN ('fixed', 'param', 'enum')),
            CHECK (operator IN ('=', '!=', '<', '<=', '>', '>=', 'LIKE', 'IN'))
        );
        CREATE TABLE IF NOT EXISTS tool_db_filter_values (
            tool_id TEXT NOT NULL,
            filter_id TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (tool_id, filter_id, value)
        );
        CREATE TABLE IF NOT EXISTS tool_db_joins (
            tool_id TEXT NOT NULL,
            join_id TEXT NOT NULL,
            left_table TEXT NOT NULL,
            left_column TEXT NOT NULL,
            right_table TEXT NOT NULL,
            right_column TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tool_id, join_id)
        );
        CREATE TABLE IF NOT EXISTS db_reader_fixed_joins (
            capsule_id TEXT NOT NULL,
            join_id TEXT NOT NULL,
            left_table TEXT NOT NULL,
            left_column TEXT NOT NULL,
            right_table TEXT NOT NULL,
            right_column TEXT NOT NULL,
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (capsule_id, join_id)
        );
        CREATE TABLE IF NOT EXISTS tool_db_params (
            tool_id TEXT NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'string',
            description TEXT NOT NULL DEFAULT '',
            required INTEGER NOT NULL DEFAULT 0,
            default_text TEXT NOT NULL DEFAULT '',
            position INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (tool_id, name)
        );
        CREATE TABLE IF NOT EXISTS tool_db_param_enums (
            tool_id TEXT NOT NULL,
            param_name TEXT NOT NULL,
            value TEXT NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (tool_id, param_name, value)
        );
        CREATE TABLE IF NOT EXISTS db_reader_fixed_params (
            capsule_id TEXT NOT NULL,
            param_name TEXT NOT NULL,
            value_text TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (capsule_id, param_name)
        );
        DELETE FROM llm_point_tools WHERE tool_id='db_read';
        DELETE FROM tools WHERE id='db_read';
        """
    )
