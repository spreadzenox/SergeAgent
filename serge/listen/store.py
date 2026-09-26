#!/usr/bin/env python3
"""Store écoute : pages collectées, dédupliquées par identifiant stable."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from serge.db.store import utcnow


def save_docs(
    conn: sqlite3.Connection,
    docs: Sequence[dict[str, str]],
    now: str | None = None,
) -> int:
    """Sauvegarde (dédup par id stable). Retourne les nouveaux.

    Args:
        conn: Connexion canon (commit par l'appelant).
        docs: Docs collecteurs (id, source, title, url, excerpt...).
        now: ISO fetched_at (défaut : maintenant).

    Returns:
        Nombre de docs insérés (doublons ignorés).
    """
    moment = now or utcnow()
    fresh = 0
    for doc in docs:
        cursor = conn.execute(
            'INSERT OR IGNORE INTO listen_docs(id, source, url, title,'
            ' excerpt, published, fetched_at, cluster_id)'
            ' VALUES(?,?,?,?,?,?,?,?)',
            (
                doc.get('id'),
                doc.get('source', ''),
                doc.get('url', ''),
                doc.get('title', ''),
                doc.get('excerpt', ''),
                doc.get('published', ''),
                moment,
                '',
            ),
        )
        fresh += cursor.rowcount or 0
    return fresh
