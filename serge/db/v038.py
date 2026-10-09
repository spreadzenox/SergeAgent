#!/usr/bin/env python3
"""Migration v38 : les tickets en base et en message privé (lot 8 bis).

Décisions Q85 et Q86 :

- ``ticket_types`` : les types de tickets, remplis depuis
  ``config/ticket-types.yaml`` (seulement les types nouveaux). Le délai
  d'expiration (``expiry_minutes``, vide : pas d'expiration), la décision
  par défaut annoncée et les boutons se règlent dans Mission Control ; le
  reste de la déclaration est dans ``spec_json``.
- ``discord_admins`` : les administrateurs Discord de Serge, ajoutés par
  leur identifiant dans Mission Control. Chacun reçoit chaque ticket en
  message privé.
- ``ticket_messages`` : le message privé envoyé à chaque administrateur
  pour chaque ticket, et l'état du ticket qu'il montre : un ticket tranché
  est mis à jour chez tous.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS ticket_types (
    id TEXT PRIMARY KEY,
    expiry_minutes INTEGER,
    default_detail TEXT NOT NULL DEFAULT '',
    buttons_json TEXT NOT NULL DEFAULT '[]',
    spec_json TEXT NOT NULL DEFAULT '{}',
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS discord_admins (
    user_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    added_by TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ticket_messages (
    ticket_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    message_id TEXT NOT NULL,
    shown_state TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (ticket_id, user_id)
);
"""


def apply_v038(connection: sqlite3.Connection) -> None:
    """Crée les types de tickets, les administrateurs et leurs messages."""
    connection.executescript(SCRIPT)
