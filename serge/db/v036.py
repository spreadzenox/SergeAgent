#!/usr/bin/env python3
"""Migration v36 : effacer les contacts des anciens essais, une seule fois.

Demandé par Clem le 7 octobre 2026 (décision Q81), au moment où le canal
e-mail est branché : un contact resté d'un ancien essai recevrait une
réponse automatique s'il écrivait à Serge. Une migration ne tourne qu'une
fois par base : les contacts créés ensuite ne sont jamais touchés.

- Effacés : les contacts et leurs adresses.
- Gardés : la liste de blocage et les accords (une personne qui s'est
  désinscrite le reste), les envois et messages reçus de ces contacts
  (l'historique), et le journal, qui note combien de contacts ont été
  effacés.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime


def apply_v036(connection: sqlite3.Connection) -> None:
    """Efface les contacts et leurs adresses ; le note au journal."""
    count = int(
        connection.execute('SELECT COUNT(*) FROM contacts').fetchone()[0]
    )
    connection.execute('DELETE FROM contact_addresses')
    connection.execute('DELETE FROM contacts')
    if count:
        connection.execute(
            'INSERT INTO events(ts, actor, type, payload_json)'
            " VALUES(?, 'migration', 'contacts.cleared', ?)",
            (
                datetime.now(UTC).isoformat(),
                json.dumps({'contacts': count, 'decision': 'Q81'}),
            ),
        )
