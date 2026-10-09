#!/usr/bin/env python3
"""Migration v37 : chaque appel au modèle garde sa tâche.

``llm_usage.task_id`` : la tâche pour laquelle le modèle a été appelé, vide
pour les appels faits hors d'une tâche et pour ceux d'avant cette version.
Il rattache le coût réel d'un appel à son business (le paramètre
``venture_id`` de la tâche), pour les points par euro dépensé de la grille
de points (lot 9, décision Q84).
"""

from __future__ import annotations

import sqlite3


def apply_v037(connection: sqlite3.Connection) -> None:
    """Ajoute la tâche de chaque appel au modèle."""
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(llm_usage)')
    }
    if 'task_id' not in colonnes:
        connection.execute(
            "ALTER TABLE llm_usage ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"
        )
    connection.execute(
        'CREATE INDEX IF NOT EXISTS idx_llm_usage_task ON llm_usage(task_id)'
    )
