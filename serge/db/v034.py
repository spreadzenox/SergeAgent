#!/usr/bin/env python3
"""Migration v34 : la page de chaque famille de réglages, et des textes
envoyés au modèle qu'on peut remettre.

- ``policy_sections.page`` : la page de Mission Control qui montre la
  famille, ``policy`` (Argent, Lecture du web…) ou ``pipeline`` (Appels au
  modèle, Outils, Recommandation de modèle), décision Q68 (point 5).
- ``serge_texts`` : un titre et une aide pour chaque texte (« Qui est
  Serge », « Quand le modèle ne peut plus appeler d'outils »…), et sa
  valeur précédente (qui l'a remplacée, quand) pour « Remettre ».
"""

from __future__ import annotations

import sqlite3


def _add(conn: sqlite3.Connection, table: str, column: str, sql: str) -> None:
    have = {str(r[1]) for r in conn.execute(f'PRAGMA table_info({table})')}
    if column not in have:
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {column} {sql}')


def apply_v034(connection: sqlite3.Connection) -> None:
    """Ajoute la page des familles et la description des textes."""
    _add(
        connection,
        'policy_sections',
        'page',
        "TEXT NOT NULL DEFAULT 'policy' CHECK (page IN ('policy', 'pipeline'))",
    )
    for column in ('title', 'help', 'previous_body', 'previous_at'):
        _add(connection, 'serge_texts', column, "TEXT NOT NULL DEFAULT ''")
    _add(connection, 'serge_texts', 'previous_by', "TEXT NOT NULL DEFAULT ''")
    _add(connection, 'serge_texts', 'updated_by', "TEXT NOT NULL DEFAULT ''")
