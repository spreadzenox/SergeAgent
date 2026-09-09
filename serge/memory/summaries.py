#!/usr/bin/env python3
"""Couche 4 : résumés régénérables, versionnés (N-1 gardé).

Un résumé par (kind, subject) : put bump version + previous. SERGE.md =
kind 'serge_md' (diff + rollback via previous). Toujours régénérable :
supprimer = reconstruit (appelant).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.db.store import utcnow


def _summary_id(kind: str, subject_id: str) -> str:
    return f'sum_{kind}_{subject_id or "global"}'


def put_summary(
    conn: sqlite3.Connection,
    kind: str,
    content: str,
    subject_id: str = '',
) -> dict[str, Any]:
    """Écrit (ou versionne) un résumé.

    Args:
        conn: Connexion canon (commit par l'appelant).
        kind: serge_md | thread | venture | ticket | digest.
        content: Contenu markdown.
        subject_id: Sujet ('' = global).

    Returns:
        Dict id/version (version 1 = création).
    """
    summary_id = _summary_id(kind, subject_id)
    moment = utcnow()
    row = conn.execute(
        'SELECT version, content FROM summaries WHERE id=?', (summary_id,)
    ).fetchone()
    if row is None:
        conn.execute(
            'INSERT INTO summaries(id, kind, subject_id, content, version,'
            " previous, created_at, updated_at) VALUES(?,?,?,?,1,'',?,?)",
            (summary_id, kind, subject_id, content, moment, moment),
        )
        return {'id': summary_id, 'version': 1}
    version = int(row[0]) + 1
    conn.execute(
        'UPDATE summaries SET content=?, version=?, previous=?,'
        ' updated_at=? WHERE id=?',
        (content, version, str(row[1]), moment, summary_id),
    )
    return {'id': summary_id, 'version': version}


def get_summary(
    conn: sqlite3.Connection, kind: str, subject_id: str = ''
) -> dict[str, Any] | None:
    """Lit un résumé (+ version + previous pour diff/rollback).

    Args:
        conn: Connexion canon (lecture).
        kind: Type de résumé.
        subject_id: Sujet ('' = global).

    Returns:
        Dict ou None si absent.
    """
    row = conn.execute(
        'SELECT id, kind, subject_id, content, version, previous, updated_at'
        ' FROM summaries WHERE id=?',
        (_summary_id(kind, subject_id),),
    ).fetchone()
    if not row:
        return None
    return {
        'id': row[0],
        'kind': row[1],
        'subject_id': row[2],
        'content': row[3],
        'version': row[4],
        'previous': row[5],
        'updated_at': row[6],
    }


def rollback_summary(
    conn: sqlite3.Connection, kind: str, subject_id: str = ''
) -> bool:
    """Rollback 1 clic (previous redevient courant, version +1).

    Args:
        conn: Connexion canon (commit par l'appelant).
        kind: Type de résumé.
        subject_id: Sujet.

    Returns:
        True si un rollback a eu lieu.
    """
    current = get_summary(conn, kind, subject_id)
    if not current or not current['previous']:
        return False
    put_summary(conn, kind, str(current['previous']), subject_id)
    return True


def serge_md_text(conn: sqlite3.Connection) -> str:
    """SERGE.md courant (contexte fixed universel, '' si absent).

    Args:
        conn: Connexion canon (lecture).

    Returns:
        Le markdown ou ''.
    """
    found = get_summary(conn, 'serge_md')
    return str(found['content']) if found else ''
