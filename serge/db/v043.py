#!/usr/bin/env python3
"""Migration v43 : « Ma réponse » change aussi l'objet ; une nouvelle
version d'un ticket repart en bas de son fil.

- ``ticket_answers.subject`` : l'objet saisi avec « Ma réponse » (une
  réponse par e-mail) ; sans objet saisi, celui du message.
- ``ticket_posts.message_id`` : le message du fil qui porte la carte
  actuelle du ticket (vide : le premier message du fil). Un ticket rouvert
  après « Réécrire » repart en bas du fil, avec une mention.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
ALTER TABLE ticket_answers ADD COLUMN subject TEXT NOT NULL DEFAULT '';
ALTER TABLE ticket_posts ADD COLUMN message_id TEXT NOT NULL DEFAULT '';
"""


def apply_v043(connection: sqlite3.Connection) -> None:
    """Ajoute l'objet d'une réponse et le message de la carte actuelle."""
    connection.executescript(SCRIPT)
