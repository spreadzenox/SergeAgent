#!/usr/bin/env python3
"""Migration v32 : annuler les tâches d'une ligne qui change d'état.

``task_cancel_rules`` : une règle par ligne. « Quand une ligne de
``table_name`` passe à ``column_name`` = ``value``, les tâches en attente
dont le paramètre ``param_name`` vaut le numéro de cette ligne sont
annulées. » Exemple : un cycle d'écoute abandonné (``listen_cycles.status``
= ``ABANDONED``) annule ses tâches en attente (paramètre ``cycle_id``) :
abandonner un cycle arrête sa chaîne.

C'est une protection réglée sur la table, comme les changements de statut
permis : le code d'écriture l'applique, quelle que soit l'invocation.

Conception : ``docs/LOT7_CONCEPTION.md``, partie 3.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS task_cancel_rules (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    value TEXT NOT NULL,
    param_name TEXT NOT NULL,
    PRIMARY KEY (table_name, column_name, value, param_name)
);
"""


def apply_v032(connection: sqlite3.Connection) -> None:
    """Crée les règles d'annulation des tâches."""
    connection.executescript(SCRIPT)
