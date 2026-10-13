#!/usr/bin/env python3
"""Élargir une liste fermée d'une contrainte CHECK, sans recréer la table.

SQLite ne sait pas modifier une contrainte. Quand une liste de valeurs
permises s'agrandit (un niveau de modèle de plus, une source de plus pour
un paramètre de lien), aucune ligne existante ne peut la violer : on
réécrit alors le schéma enregistré, comme la documentation de SQLite le
permet pour ce cas, au lieu de recopier toute la table.
"""

from __future__ import annotations

import sqlite3


def widen_check(
    connection: sqlite3.Connection, table: str, avant: str, apres: str
) -> bool:
    """Remplace ``avant`` par ``apres`` dans le schéma de ``table``.

    Exemple : ``"'mid', 'smart')"`` devient ``"'mid', 'smart', 'code')"``.
    Rien n'est fait si ``avant`` n'y est pas (déjà élargi).

    Returns:
        Vrai si le schéma a changé.
    """
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    sql = str(row[0]) if row else ''
    if avant not in sql:
        return False
    version = int(connection.execute('PRAGMA schema_version').fetchone()[0])
    connection.execute('PRAGMA writable_schema=ON')
    connection.execute(
        "UPDATE sqlite_master SET sql=? WHERE type='table' AND name=?",
        (sql.replace(avant, apres), table),
    )
    connection.execute(f'PRAGMA schema_version={version + 1}')
    connection.execute('PRAGMA writable_schema=OFF')
    return True
