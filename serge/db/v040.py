#!/usr/bin/env python3
"""Migration v40 : une case à cocher dans le formulaire d'un bouton.

Un paramètre d'un déclencheur « bouton » peut venir d'une case du
formulaire (source ``form_case``) : cochée, il vaut ``1`` ; sinon ``0``.
Exemple : « Valider chaque brouillon » sur le bouton « Lancer un essai »,
pour que le business d'essai naisse en mode validation. SQLite ne sait pas
modifier une contrainte : la table est recréée, avec ses lignes.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS trigger_params_v40 (
    trigger_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL
        CHECK (source IN ('row', 'form', 'form_case', 'fixed')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (trigger_id, param_name)
);
INSERT INTO trigger_params_v40 SELECT * FROM trigger_params;
DROP TABLE trigger_params;
ALTER TABLE trigger_params_v40 RENAME TO trigger_params;
"""


def apply_v040(connection: sqlite3.Connection) -> None:
    """Ajoute la source ``form_case`` aux paramètres des déclencheurs."""
    connection.executescript(SCRIPT)
