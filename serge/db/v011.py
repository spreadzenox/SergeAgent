#!/usr/bin/env python3
"""Migration v11 : catalogue des canaux d’écriture + jonction briques."""

from __future__ import annotations

import sqlite3


def apply_v011(connection: sqlite3.Connection) -> None:
    """Crée ``canaux`` et ``brique_canaux``.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS canaux (
            id TEXT PRIMARY KEY,
            titre TEXT NOT NULL DEFAULT '',
            doc_md TEXT NOT NULL DEFAULT '',
            code_path TEXT NOT NULL DEFAULT '',
            code_sha TEXT NOT NULL DEFAULT '',
            etat TEXT NOT NULL DEFAULT 'branche',
            files_sha TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT ''
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS brique_canaux (
            canal_id TEXT NOT NULL,
            brique_kind TEXT NOT NULL,
            brique_id TEXT NOT NULL,
            PRIMARY KEY (canal_id, brique_kind, brique_id)
        )
        """
    )
