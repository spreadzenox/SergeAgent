#!/usr/bin/env python3
"""Store écoute : docs collectés + assignation clusters (dét)."""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from typing import Any

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


def unclustered(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    """Docs sans cluster (batch hebdo).

    Args:
        conn: Connexion canon (lecture).
        limit: Cap batch.

    Returns:
        Docs [{id, title, excerpt}].
    """
    rows = conn.execute(
        'SELECT id, title, excerpt FROM listen_docs WHERE cluster_id=?'
        ' ORDER BY fetched_at ASC LIMIT ?',
        ('', max(1, limit)),
    ).fetchall()
    return [{'id': row[0], 'title': row[1], 'excerpt': row[2]} for row in rows]


def set_cluster(
    conn: sqlite3.Connection, doc_ids: Sequence[str], cluster_id: str
) -> int:
    """Assigne un cluster (dét, réversible : '' = bruit).

    Args:
        conn: Connexion canon (commit par l'appelant).
        doc_ids: Docs à marquer.
        cluster_id: Id cluster (k1...).

    Returns:
        Nombre marqués.
    """
    ids = list(doc_ids)
    if not ids:
        return 0
    cursor = conn.execute(
        f'UPDATE listen_docs SET cluster_id=? WHERE id IN ({",".join("?" * len(ids))})',
        [cluster_id, *ids],
    )
    return cursor.rowcount or 0


def docs_in_cluster(
    conn: sqlite3.Connection, cluster_id: str
) -> list[dict[str, Any]]:
    """Docs d'un cluster (verbatims pour J1).

    Args:
        conn: Connexion canon (lecture).
        cluster_id: Id cluster.

    Returns:
        Docs [{id, title, excerpt}].
    """
    rows = conn.execute(
        'SELECT id, title, excerpt FROM listen_docs WHERE cluster_id=?',
        (cluster_id,),
    ).fetchall()
    return [{'id': row[0], 'title': row[1], 'excerpt': row[2]} for row in rows]
