#!/usr/bin/env python3
"""Migration v31 : le prix maximum et la tolérance de chaque niveau de modèle.

La page Pipeline recommande, pour chaque niveau, le modèle au meilleur
rapport note / prix. Deux réglages par niveau, rangés avec son modèle dans
``llm_models`` et modifiables dans Mission Control :

- ``max_price_usd`` : le prix maximum, en dollars par million de jetons
  (0 : pas encore réglé, rien n'est recommandé) ;
- ``tolerance_pct`` : la part, en pourcentage, de la meilleure note sous ce
  prix qu'un modèle doit avoir pour être retenu (100 : seulement le meilleur).
  Un entier, parce que SQLite refuse d'ajouter à une table déjà remplie une
  colonne ``NOT NULL`` au défaut décimal avec une contrainte ``CHECK``.

Les valeurs de départ de chaque niveau sont dans ``config/pipeline.yaml``.
"""

from __future__ import annotations

import sqlite3


def apply_v031(connection: sqlite3.Connection) -> None:
    """Ajoute le prix maximum et la tolérance de chaque niveau."""
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(llm_models)')
    }
    if 'max_price_usd' not in colonnes:
        connection.execute(
            'ALTER TABLE llm_models ADD COLUMN max_price_usd REAL NOT NULL'
            ' DEFAULT 0 CHECK (max_price_usd >= 0)'
        )
    if 'tolerance_pct' not in colonnes:
        connection.execute(
            'ALTER TABLE llm_models ADD COLUMN tolerance_pct INTEGER NOT NULL'
            ' DEFAULT 95 CHECK (tolerance_pct BETWEEN 1 AND 100)'
        )
