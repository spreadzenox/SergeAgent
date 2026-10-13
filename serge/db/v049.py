#!/usr/bin/env python3
"""Migration v49 : l'étape 5, le vrai produit (lot 10, Q43 et Q91).

- ``customer_requests`` reçoit son état : ``new`` (pas encore vue par la
  conception du produit), ``kept`` (retenue), ``refused`` (refusée, avec
  sa raison) ou ``delivered`` (livrée). ``plan_id`` : le plan du produit
  qui l'a retenue ou refusée ; ``delivered_version`` : la version qui l'a
  livrée. Exemple : « exporter le devis en PDF », retenue par le plan
  du produit, livrée en v3.
- ``product_plans.domain`` : le nom de domaine que propose le plan d'un
  produit fini, validé dans le ticket « Plan », puis acheté par Serge.
"""

from __future__ import annotations

import sqlite3

COLONNES = (
    (
        'customer_requests',
        'status',
        "TEXT NOT NULL DEFAULT 'new'"
        " CHECK (status IN ('new', 'kept', 'refused', 'delivered'))",
    ),
    ('customer_requests', 'reason', "TEXT NOT NULL DEFAULT ''"),
    ('customer_requests', 'plan_id', "TEXT NOT NULL DEFAULT ''"),
    ('customer_requests', 'delivered_version', 'INTEGER NOT NULL DEFAULT 0'),
    ('customer_requests', 'updated_at', "TEXT NOT NULL DEFAULT ''"),
    ('product_plans', 'domain', "TEXT NOT NULL DEFAULT ''"),
)


def apply_v049(connection: sqlite3.Connection) -> None:
    """Ajoute l'état des demandes des clients et le domaine d'un plan."""
    for table, colonne, definition in COLONNES:
        existantes = {
            str(r[1])
            for r in connection.execute(f'PRAGMA table_info({table})')
        }
        if colonne not in existantes:
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN {colonne} {definition}'
            )
