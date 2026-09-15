#!/usr/bin/env python3
"""Migration v12 : trace de contact par lieu (venue / handle / URL)."""

from __future__ import annotations

import sqlite3


def apply_v012(connection: sqlite3.Connection) -> None:
    """Ajoute venue, handle, profile_url sur ``contacts``.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    have = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(contacts)')
    }
    for name, decl in (
        ('venue', "TEXT NOT NULL DEFAULT ''"),
        ('handle', "TEXT NOT NULL DEFAULT ''"),
        ('profile_url', "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in have:
            connection.execute(
                f'ALTER TABLE contacts ADD COLUMN {name} {decl}'
            )
    connection.execute(
        'CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_trace'
        ' ON contacts(venture_id, venue, handle)'
        " WHERE venue!='' AND handle!=''"
    )
