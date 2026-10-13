#!/usr/bin/env python3
"""Migration v43 : le niveau « code » et les captures (lot 10, Q91).

- Le niveau « code » devient permis pour une invocation
  (``invocations.model_tier``) et dans ``llm_models``. Les deux colonnes
  avaient une liste fermée (``fast``, ``mid``, ``smart``) : on l'élargit
  dans le schéma enregistré, comme SQLite le permet pour une contrainte
  qu'aucune ligne existante ne peut violer (``serge.db.contrainte``).
- ``llm_models.needs_image`` : le modèle du niveau doit lire les images
  (1 pour « code » : le constructeur et le relecteur voient des captures).
- ``artifacts`` : la taille du fichier (``size_bytes``) et la tâche qui l'a
  produit (``task_id``), pour montrer les captures sur la fiche de la tâche.
"""

from __future__ import annotations

import sqlite3

from serge.db.contrainte import widen_check

_AVANT = "'mid', 'smart')"
_APRES = "'mid', 'smart', 'code')"


def _colonnes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    }


def apply_v043(connection: sqlite3.Connection) -> None:
    """Permet le niveau « code » ; ajoute les colonnes des captures."""
    widen_check(connection, 'invocations', _AVANT, _APRES)
    widen_check(connection, 'llm_models', _AVANT, _APRES)
    if 'needs_image' not in _colonnes(connection, 'llm_models'):
        connection.execute(
            'ALTER TABLE llm_models ADD COLUMN needs_image INTEGER NOT NULL'
            ' DEFAULT 0 CHECK (needs_image IN (0, 1))'
        )
    colonnes = _colonnes(connection, 'artifacts')
    if 'size_bytes' not in colonnes:
        connection.execute(
            'ALTER TABLE artifacts ADD COLUMN size_bytes INTEGER NOT NULL'
            ' DEFAULT 0'
        )
    if 'task_id' not in colonnes:
        connection.execute(
            "ALTER TABLE artifacts ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"
        )
