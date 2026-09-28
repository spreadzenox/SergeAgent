#!/usr/bin/env python3
"""Migration v27 : ce que voit une invocation, et l'historique d'une ligne.

- ``table_views`` : une ligne par table qu'une invocation peut voir, avec
  son titre, ce qu'elle contient et la colonne qui dit quelles lignes sont
  les plus récentes (par exemple ``created_at``).
- ``table_view_columns`` : les colonnes lisibles de chaque table. Celles
  marquées ``short`` forment sa version courte (pour un business, son
  numéro et son nom). Une colonne absente n'est jamais lue.
- ``invocation_compare_tables`` : les ajustements du deuxième cercle d'une
  invocation. Par défaut, elle voit la version courte des tables où elle
  écrit ; ``included`` = 1 ajoute une table, 0 en retire une.
- ``event_rows`` : quel événement du journal concerne quelle ligne. C'est
  ce que lit « Lire l'historique ». Les anciens événements sont repris :
  ceux d'un business (``venture_id``) et les écritures des invocations.
- ``task_seen_tables`` : pour chaque tâche, combien de lignes de chaque
  table elle a reçues pour comparer, et combien ont été laissées de côté
  (``lessons`` pour ses leçons). Mission Control l'affiche.

Conception : ``docs/LOT6_CONCEPTION.md``, partie 16.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS table_views (
    table_name TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    order_column TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS table_view_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    short INTEGER NOT NULL DEFAULT 0 CHECK (short IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (table_name, column_name)
);
CREATE TABLE IF NOT EXISTS invocation_compare_tables (
    invocation_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    included INTEGER NOT NULL CHECK (included IN (0, 1)),
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (invocation_id, table_name)
);
CREATE TABLE IF NOT EXISTS event_rows (
    event_id INTEGER NOT NULL,
    table_name TEXT NOT NULL,
    row_id TEXT NOT NULL,
    PRIMARY KEY (table_name, row_id, event_id)
);
CREATE TABLE IF NOT EXISTS task_seen_tables (
    task_id TEXT NOT NULL,
    table_name TEXT NOT NULL,
    rows_given INTEGER NOT NULL DEFAULT 0,
    rows_left_out INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, table_name)
);

INSERT OR IGNORE INTO event_rows(event_id, table_name, row_id)
    SELECT id, 'ventures', venture_id FROM events WHERE venture_id<>'';
INSERT OR IGNORE INTO event_rows(event_id, table_name, row_id)
    SELECT id, json_extract(payload_json, '$.table'),
        CAST(json_extract(payload_json, '$.id') AS TEXT)
    FROM events
    WHERE type LIKE 'write.%' AND json_valid(payload_json)
        AND json_extract(payload_json, '$.table') IS NOT NULL
        AND json_extract(payload_json, '$.id') IS NOT NULL;
"""


def apply_v027(connection: sqlite3.Connection) -> None:
    """Crée les vues des tables, les tables à comparer et l'historique."""
    connection.executescript(SCRIPT)
