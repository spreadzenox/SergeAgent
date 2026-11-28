#!/usr/bin/env python3
"""Migration v61 : Serge a plusieurs boîtes e-mail (décision Q120).

Deux colonnes :

- ``touches.sender`` : la boîte d'où l'envoi est parti
  (``serge.chevalier@jpesquet.tech``). Vide : la boîte du serveur, celle de
  ``gog.env`` ; c'est le cas de tous les envois d'avant ;
- ``inbound_events.mailbox`` : la boîte qui a reçu le message. Vide : la
  boîte du serveur.

Une conversation reste sur sa boîte : la réponse à un message part de la
boîte qui l'a reçu, une relance de celle du premier message
(``serge/conversations/mailbox.py``).
"""

from __future__ import annotations

import sqlite3


def _add(connection: sqlite3.Connection, table: str, column: str) -> None:
    have = {
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    }
    if column not in have:
        connection.execute(
            f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''"
        )


def apply_v061(connection: sqlite3.Connection) -> None:
    """Ajoute la boîte d'un envoi et celle d'un message reçu."""
    _add(connection, 'touches', 'sender')
    _add(connection, 'inbound_events', 'mailbox')
