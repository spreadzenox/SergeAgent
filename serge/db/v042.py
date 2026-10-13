#!/usr/bin/env python3
"""Migration v42 : les chantiers, où Serge code ses produits (lot 10, Q91).

- ``sandboxes`` : un chantier par business et par livrable. C'est un
  conteneur Docker, gardé entre deux tâches, avec son volume monté sur
  ``/work`` ; la table dit s'il tourne, la place qu'il prend sur le disque
  et pourquoi il a été arrêté (« le chantier prend 21 000 Mo, plus que les
  20 480 permis »).
- ``tasks.answer_json`` : la réponse d'une tâche LLM, telle que le modèle
  l'a rendue (après vérification du format), pour la fiche de la tâche
  dans Mission Control. Exemple : le compte rendu de « Essayer le
  chantier ».
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS sandboxes (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL DEFAULT '',
    deliverable TEXT NOT NULL DEFAULT '',
    profile TEXT NOT NULL DEFAULT '',
    container TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running', 'stopped', 'removed')),
    disk_mb INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    last_command_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def apply_v042(connection: sqlite3.Connection) -> None:
    """Crée la table des chantiers ; garde la réponse des tâches."""
    connection.executescript(SCRIPT)
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(tasks)')
    }
    if 'answer_json' not in colonnes:
        connection.execute(
            "ALTER TABLE tasks ADD COLUMN answer_json TEXT NOT NULL DEFAULT ''"
        )
