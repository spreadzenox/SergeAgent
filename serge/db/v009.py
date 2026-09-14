#!/usr/bin/env python3
"""Migration v9 : catalogue des invocations techniques."""

from __future__ import annotations

import sqlite3


def apply_v009(connection: sqlite3.Connection) -> None:
    """Crée ``tech_invocations`` (types déterministes rattachés à une étape).

    Args:
        connection: Connexion (commit par l’appelant).
    """
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tech_invocations (
            id TEXT PRIMARY KEY,
            etape_id TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL,
            code_path TEXT NOT NULL DEFAULT '',
            code_sha TEXT NOT NULL DEFAULT '',
            titre TEXT NOT NULL DEFAULT '',
            doc_md TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1
        )
        """
    )
