#!/usr/bin/env python3
"""Migration v30 : le vrai coût des appels, et les modifications du pipeline.

- ``llm_usage.cost_usd`` : ce qu'OpenRouter a vraiment facturé pour un
  appel au modèle, en dollars (ses « crédits »). Vide quand le fournisseur
  ne le donne pas : la dépense est alors estimée à partir des jetons.
- ``pipeline_changes`` : les modifications d'objets déjà en base, décrites
  dans la section ``changes`` de ``config/pipeline.yaml``. Chacune n'est
  appliquée qu'une fois par instance, et seulement si la valeur en base est
  encore celle d'origine. Exemple : passer les tours d'outils d'« Explorer
  le web » de 25 à 10, sans toucher une valeur que Julien aurait changée.

Conception : ``docs/LOT7_CONCEPTION.md``, parties 3 et 5.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS pipeline_changes (
    id TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT ''
);
"""


def apply_v030(connection: sqlite3.Connection) -> None:
    """Ajoute le coût réel des appels et le suivi des modifications."""
    connection.executescript(SCRIPT)
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(llm_usage)')
    }
    if 'cost_usd' not in colonnes:
        connection.execute('ALTER TABLE llm_usage ADD COLUMN cost_usd REAL')
