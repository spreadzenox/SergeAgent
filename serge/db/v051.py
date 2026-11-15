#!/usr/bin/env python3
"""Migration v51 : ce que coûte un appel, une tâche gelée, le niveau « web ».

- ``llm_usage.provider``, ``cached_tokens``, ``cache_write_tokens`` : chez
  qui OpenRouter a envoyé l'appel, et combien de jetons ont été lus ou
  écrits dans le cache. Exemple : un appel de 168 000 jetons chez Anthropic
  dont 160 000 lus en cache coûte dix fois moins qu'un appel sans cache ;
  sans ces colonnes, on ne voit pas pourquoi une tâche a coûté cher.
- ``tasks.status`` peut valoir ``blocked`` : une tâche gelée attend la
  réponse de Julien à une demande qu'elle lui a faite (ticket REQUESTED) ;
  elle repart quand il répond.
- le niveau de modèle ``web`` (voir et cliquer des pages, pour le
  relecteur) devient permis pour une invocation et dans ``llm_models``.
"""

from __future__ import annotations

import sqlite3

from serge.db.contrainte import widen_check


def apply_v051(connection: sqlite3.Connection) -> None:
    """Ajoute les colonnes du cache, le statut gelé et le niveau « web »."""
    colonnes = {
        str(r[1]) for r in connection.execute('PRAGMA table_info(llm_usage)')
    }
    for nom, sorte in (
        ('provider', "TEXT NOT NULL DEFAULT ''"),
        ('cached_tokens', 'INTEGER NOT NULL DEFAULT 0'),
        ('cache_write_tokens', 'INTEGER NOT NULL DEFAULT 0'),
    ):
        if nom not in colonnes:
            connection.execute(
                f'ALTER TABLE llm_usage ADD COLUMN {nom} {sorte}'
            )
    widen_check(
        connection, 'tasks', "'cancelled'))", "'cancelled', 'blocked'))"
    )
    for table in ('invocations', 'llm_models'):
        widen_check(
            connection, table, "'smart', 'code')", "'smart', 'code', 'web')"
        )
