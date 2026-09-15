#!/usr/bin/env python3
"""Migration v13 : login et mot de passe en clair sur accounts_standing."""

from __future__ import annotations

import sqlite3


def apply_v013(connection: sqlite3.Connection) -> None:
    """Ajoute ``login`` et ``password`` sur ``accounts_standing``.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    have = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(accounts_standing)')
    }
    for name, decl in (
        ('login', "TEXT NOT NULL DEFAULT ''"),
        ('password', "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in have:
            connection.execute(
                f'ALTER TABLE accounts_standing ADD COLUMN {name} {decl}'
            )
