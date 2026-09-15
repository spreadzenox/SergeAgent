#!/usr/bin/env python3
"""Migration v14 : dernier usage d’un compte standing."""

from __future__ import annotations

import sqlite3


def apply_v014(connection: sqlite3.Connection) -> None:
    """Ajoute ``last_used_at`` sur ``accounts_standing``.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    have = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(accounts_standing)')
    }
    if 'last_used_at' not in have:
        connection.execute(
            'ALTER TABLE accounts_standing ADD COLUMN last_used_at'
            " TEXT NOT NULL DEFAULT ''"
        )
