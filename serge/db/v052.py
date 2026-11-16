#!/usr/bin/env python3
"""Migration v52 : les business d'essai sont à part (lot 12, décision Q98).

- ``ventures.trial`` : 1 pour un business créé par un bouton d'essai de la
  page Système (« Lancer un essai », « Essayer l'étape 2 », les deux
  « Bout en bout » d'une calculatrice). Un business d'essai sert à essayer
  une brique : il ne prend aucune place de test, et la chaîne réelle ne
  part jamais pour lui. Les business d'essai déjà en base sont marqués :
  ceux au statut ``TEST``, et ceux dont la raison du choix commence par
  « Essai » (c'est ce qu'écrivent les boutons d'essai).
- ``table_quotas.where_column`` et ``where_value`` : un quota peut ne
  compter que certaines lignes. Exemple : les places de test comptent les
  business dont ``trial`` vaut 0 ; la calculatrice d'un essai n'en prend
  pas.
"""

from __future__ import annotations

import sqlite3


def _colonnes(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    }


def apply_v052(connection: sqlite3.Connection) -> None:
    """Ajoute ``ventures.trial`` et le filtre d'un quota."""
    if 'trial' not in _colonnes(connection, 'ventures'):
        connection.execute(
            'ALTER TABLE ventures ADD COLUMN trial INTEGER NOT NULL DEFAULT 0'
            ' CHECK (trial IN (0, 1))'
        )
        connection.execute(
            "UPDATE ventures SET trial=1 WHERE lifecycle='TEST'"
            " OR choice_reason LIKE 'Essai %'"
        )
    quotas = _colonnes(connection, 'table_quotas')
    for nom in ('where_column', 'where_value'):
        if nom not in quotas:
            connection.execute(
                f'ALTER TABLE table_quotas ADD COLUMN {nom} TEXT NOT NULL'
                " DEFAULT ''"
            )
