#!/usr/bin/env python3
"""Migration v28 : les paramètres d'un passage qui attend un clic.

Un lien réglé « à la main » (``links.auto`` = 0) note le passage et
attend le clic de Julien dans Mission Control. Pour lancer l'invocation
suivante au moment du clic, avec les bons paramètres, on les garde :
``link_passage_params``, une ligne par paramètre. Exemple : le lien
« le business choisi part en conception » garde ``venture_id = 12``
jusqu'au clic sur « Passer à la suite ».

Conception : ``docs/LOT6_CONCEPTION.md``, partie 18.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS link_passage_params (
    link_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (link_id, source_ref, name)
);
"""


def apply_v028(connection: sqlite3.Connection) -> None:
    """Crée la table des paramètres des passages en attente."""
    connection.executescript(SCRIPT)
