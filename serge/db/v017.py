#!/usr/bin/env python3
"""Migration v17 : suppression définitive des réglages Écoute legacy."""

from __future__ import annotations

import sqlite3


def apply_v017(connection: sqlite3.Connection) -> None:
    """Supprime la table remplacée par les snapshots Policy."""
    connection.execute('DROP TABLE IF EXISTS listen_settings')
