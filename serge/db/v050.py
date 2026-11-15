#!/usr/bin/env python3
"""Migration v50 : un verrou de prix sur un point d'entrée d'API (lot 10).

- ``api_endpoints.guard`` : un objet JSON, ou vide. Avant d'appeler un
  point d'entrée payant, « Appeler une API » vérifie le prix par un autre
  point d'entrée et refuse au-dessus d'un plafond réglé sur la page
  Policy. Exemple : l'achat d'un domaine chez Cloudflare est refusé si le
  nom n'est pas libre, s'il est premium, ou si son prix, la première année
  comme au renouvellement, dépasse le réglage « prix_max_eur ».
"""

from __future__ import annotations

import sqlite3


def apply_v050(connection: sqlite3.Connection) -> None:
    """Ajoute ``api_endpoints.guard``."""
    colonnes = {
        str(r[1])
        for r in connection.execute('PRAGMA table_info(api_endpoints)')
    }
    if 'guard' not in colonnes:
        connection.execute(
            "ALTER TABLE api_endpoints ADD COLUMN guard TEXT NOT NULL DEFAULT ''"
        )
