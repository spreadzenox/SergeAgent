#!/usr/bin/env python3
"""Migration v41 : les tickets dans le forum du serveur de Serge (Q88).

Les tickets ne partent plus en message privé à chaque administrateur : ils
ouvrent chacun un fil dans le forum « tickets » du serveur Discord de
Serge, réglé dans Mission Control.

- ``ticket_posts`` : le fil de chaque ticket (son identifiant est aussi
  celui du premier message, la carte), l'état du ticket que montre la
  carte, et si le fil est archivé (un ticket tranché).
- ``ticket_messages`` (un message privé par administrateur) est retirée.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS ticket_posts (
    ticket_id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL DEFAULT '',
    shown_state TEXT NOT NULL DEFAULT '',
    archived INTEGER NOT NULL DEFAULT 0 CHECK (archived IN (0, 1)),
    updated_at TEXT NOT NULL
);
DROP TABLE IF EXISTS ticket_messages;
"""


def apply_v041(connection: sqlite3.Connection) -> None:
    """Crée les fils des tickets et retire les messages privés."""
    connection.executescript(SCRIPT)
