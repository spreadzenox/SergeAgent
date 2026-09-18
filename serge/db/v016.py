#!/usr/bin/env python3
"""Migration v16 : noms explicites des paramètres de cycle d'écoute."""

from __future__ import annotations

import sqlite3


def apply_v016(connection: sqlite3.Connection) -> None:
    """Renomme les colonnes de cycle pour supprimer n/p ambigus."""
    connection.execute('DROP TABLE IF EXISTS listen_settings')
    columns = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(listen_cycles)')
    }
    if 'n_target' in columns and 'needs_target' not in columns:
        connection.execute(
            'ALTER TABLE listen_cycles RENAME COLUMN n_target TO needs_target'
        )
    if 'p_target' in columns and 'business_target' not in columns:
        connection.execute(
            'ALTER TABLE listen_cycles RENAME COLUMN p_target TO business_target'
        )
