#!/usr/bin/env python3
"""Migration v44 : publier un produit, en staging et en prod (lot 10, Q91).

- ``deployments`` : ce qui tourne, une ligne par cible et par chantier
  (``staging-<chantier>``, ``prod-<chantier>``) : la version, son image,
  le conteneur, le port fixe sur 127.0.0.1 (gardé d'une version à
  l'autre, pour que la route de Caddy reste juste), l'adresse publique,
  l'état et pourquoi la dernière publication a raté.
- ``artifacts.deliverable`` : le livrable d'une version ou d'une capture,
  pour numéroter les versions d'un livrable (v1, v2…).
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS deployments (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL DEFAULT '',
    deliverable TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL CHECK (target IN ('staging', 'prod')),
    version INTEGER NOT NULL DEFAULT 0,
    image TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL DEFAULT '',
    host_port INTEGER NOT NULL DEFAULT 0,
    hostname TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'failed', 'stopped')),
    last_error TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def apply_v044(connection: sqlite3.Connection) -> None:
    """Crée les publications ; le livrable d'un fichier."""
    connection.executescript(SCRIPT)
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(artifacts)')
    }
    if 'deliverable' not in colonnes:
        connection.execute(
            'ALTER TABLE artifacts ADD COLUMN deliverable TEXT NOT NULL'
            " DEFAULT ''"
        )
