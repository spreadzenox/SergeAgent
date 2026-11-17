#!/usr/bin/env python3
"""Migration v54 : les lignes d'un ticket sont retirées.

``ticket_items`` gardait les lignes d'un ticket à trancher une par une (les
leçons d'un ticket « Mémoire » : garder, modifier, jeter). Aucune
invocation n'a jamais ouvert un tel ticket, et son type est retiré
(nettoyage du 17 novembre 2026) : la table part avec lui.
"""

from __future__ import annotations

import sqlite3


def apply_v054(connection: sqlite3.Connection) -> None:
    """Retire la table des lignes d'un ticket."""
    connection.execute('DROP TABLE IF EXISTS ticket_items')
