#!/usr/bin/env python3
"""Ce que la fiche d'un business montre de son produit (lot 10, Q91).

Ses publications (staging et prod : la version, l'adresse, l'état, et
pourquoi la dernière a raté) et ses versions figées, de la plus récente à
la plus ancienne. Les plans, les critiques et les passages de construction
s'y ajoutent avec l'étape 2.
"""

from __future__ import annotations

import sqlite3
from typing import Any

CIBLES = {'staging': 'Staging', 'prod': 'Prod'}
ETATS = {'running': 'en ligne', 'failed': 'ratée', 'stopped': 'arrêtée'}


def cadres_produit(
    conn: sqlite3.Connection, venture_id: str
) -> list[dict[str, Any]]:
    """Les cadres « En ligne » et « Versions » d'un business, s'il en a."""
    cadres: list[dict[str, Any]] = []
    publications = conn.execute(
        'SELECT target, version, hostname, status, last_error, updated_at'
        ' FROM deployments WHERE venture_id=? ORDER BY target DESC',
        (venture_id,),
    ).fetchall()
    if publications:
        cadres.append(
            {
                'titre': 'En ligne',
                'champs': [
                    {
                        'k': f'{CIBLES.get(p[0], p[0])} (v{p[1]})',
                        'v': f'https://{p[2]} — {ETATS.get(p[3], p[3])}'
                        + (f' : {p[4]}' if p[4] else '')
                        + f' ({str(p[5])[:16]})',
                    }
                    for p in publications
                ],
            }
        )
    versions = conn.execute(
        'SELECT deliverable, version, path_or_url, size_bytes, created_at'
        " FROM artifacts WHERE venture_id=? AND kind='version'"
        ' ORDER BY created_at DESC LIMIT 20',
        (venture_id,),
    ).fetchall()
    if versions:
        cadres.append(
            {
                'titre': 'Versions',
                'champs': [
                    {
                        'k': f'{v[0]} v{v[1]}',
                        'v': f'{v[2]} ({int(v[3]) // 1024} Ko,'
                        f' {str(v[4])[:16]})',
                    }
                    for v in versions
                ],
            }
        )
    return cadres
