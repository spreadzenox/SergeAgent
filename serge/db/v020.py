#!/usr/bin/env python3
"""Migration v20 : métadonnées runtime des points LLM dans ``llm_points``."""

from __future__ import annotations

import sqlite3


def _add_column(
    connection: sqlite3.Connection, name: str, definition: str
) -> bool:
    columns = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(llm_points)')
    }
    if name in columns:
        return False
    connection.execute(
        f'ALTER TABLE llm_points ADD COLUMN {name} {definition}'
    )
    return True


def apply_v020(connection: sqlite3.Connection) -> None:
    """Ajoute les trois champs éditables de l’invocation.

    Les valeurs par défaut sont des valeurs de contrat valides. Le seed des
    lignes existantes est fait par ``ensure_llm_points`` après migration, afin
    que cette migration reste indépendante de la configuration d'instance.
    """
    added = _add_column(connection, 'prompt', "TEXT NOT NULL DEFAULT ''")
    added = (
        _add_column(
            connection,
            'output_mode',
            "TEXT NOT NULL DEFAULT 'text' CHECK(output_mode IN ('structured', 'text'))",
        )
        or added
    )
    added = (
        _add_column(
            connection,
            'external_info',
            'INTEGER NOT NULL DEFAULT 0 CHECK(external_info IN (0, 1))',
        )
        or added
    )
    if added:
        columns = {
            str(row[1])
            for row in connection.execute('PRAGMA table_info(llm_points)')
        }
        if 'updated_at' in columns:
            # Force one seed pass for rows inherited from v19. Later edits use
            # this existing timestamp as the durable "already initialized" mark.
            connection.execute("UPDATE llm_points SET updated_at=''")
