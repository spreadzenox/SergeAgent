#!/usr/bin/env python3
"""Migration v10 : docs MC, SHA fichiers, date, liens d’épine."""

from __future__ import annotations

import sqlite3

_CATALOGUE = ('pipeline_steps', 'tools', 'llm_points', 'tech_invocations')

_SHA_COLS = (
    ('files_sha', "TEXT NOT NULL DEFAULT ''"),
    ('updated_at', "TEXT NOT NULL DEFAULT ''"),
)

_STEP_COLS = (
    ('titre', "TEXT NOT NULL DEFAULT ''"),
    ('pourquoi', "TEXT NOT NULL DEFAULT ''"),
    ('argent', "TEXT NOT NULL DEFAULT ''"),
    ('dependance', "TEXT NOT NULL DEFAULT ''"),
    ('comment', "TEXT NOT NULL DEFAULT ''"),
    ('doc_md', "TEXT NOT NULL DEFAULT ''"),
)


def _add_col(
    connection: sqlite3.Connection, table: str, name: str, decl: str
) -> None:
    cols = {
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info({table})')
    }
    if name not in cols:
        connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')


def apply_v010(connection: sqlite3.Connection) -> None:
    """Ajoute docs/SHA/date au catalogue + table ``etape_liens``.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    for table in _CATALOGUE:
        for name, decl in _SHA_COLS:
            _add_col(connection, table, name, decl)
    for name, decl in _STEP_COLS:
        _add_col(connection, 'pipeline_steps', name, decl)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS etape_liens (
            id TEXT PRIMARY KEY,
            de TEXT NOT NULL,
            vers TEXT NOT NULL,
            libelle TEXT NOT NULL,
            debit TEXT NOT NULL,
            rang INTEGER NOT NULL DEFAULT 0,
            files_sha TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
