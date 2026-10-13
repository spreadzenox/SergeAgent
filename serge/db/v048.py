#!/usr/bin/env python3
"""Migration v48 : une écriture peut passer outre les règles de doublon
(lot 10).

- ``invocation_writes.skip_dedup`` : 1 pour une écriture qui ne consulte
  pas ``dedup_rules``. Seuls les essais de bout en bout de Mission Control
  s'en servent : « Bout en bout : le POC d'une calculatrice » crée un
  business neuf à chaque essai, alors qu'un second business « une
  calculatrice en ligne » serait sinon écarté comme doublon du premier.
"""

from __future__ import annotations

import sqlite3


def apply_v048(connection: sqlite3.Connection) -> None:
    """Ajoute ``invocation_writes.skip_dedup``."""
    colonnes = {
        str(r[1])
        for r in connection.execute('PRAGMA table_info(invocation_writes)')
    }
    if 'skip_dedup' not in colonnes:
        connection.execute(
            'ALTER TABLE invocation_writes ADD COLUMN skip_dedup INTEGER'
            ' NOT NULL DEFAULT 0'
        )
