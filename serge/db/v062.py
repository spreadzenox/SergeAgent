#!/usr/bin/env python3
"""Migration v62 : une leçon garde le business d'où elle vient.

``lessons.venture_id`` : le business dont une leçon est tirée (vide : elle
ne vient pas d'un business). Le ticket « Leçon », par lequel un humain
garde ou jette une leçon proposée, montre ainsi ce business à côté de la
leçon.

Exemple : le business « Devis artisan » est arrêté après un test sans
réponse ; la leçon « Les artisans ne répondent pas aux e-mails le lundi »
porte son numéro.
"""

from __future__ import annotations

import sqlite3


def apply_v062(connection: sqlite3.Connection) -> None:
    """Ajoute à une leçon le business d'où elle vient."""
    have = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(lessons)')
    }
    if 'venture_id' not in have:
        connection.execute(
            "ALTER TABLE lessons ADD COLUMN venture_id TEXT NOT NULL DEFAULT ''"
        )
