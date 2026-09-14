#!/usr/bin/env python3
"""Catalogue des invocations techniques (déterministes, rattachées à une étape)."""

from __future__ import annotations

import sqlite3
from typing import Any

KINDS = frozenset({'cluster', 'select', 'score', 'transform', 'index'})

# id, etape, kind, path, sha, titre, doc
SEED: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    (
        'cluster_listen',
        'pre_prospection',
        'cluster',
        'serge/listen/cluster.py',
        '',
        'Regrouper les demandes',
        'Paquets Jaccard / labels : pas une invocation LLM.',
    ),
    (
        'select_pre_venture',
        'choix_venture',
        'select',
        '',
        '',
        'Choisir une pré-venture',
        'Algo de sélection parmi les N smokes. Pas encore un module runtime.',
    ),
    (
        'memory_fts_index',
        'collect_feedback',
        'index',
        'serge/memory/search.py',
        '',
        'Indexer la mémoire',
        'FTS5 : création / maj de l’index, hors invocation LLM.',
    ),
)


class TechError(ValueError):
    """Kind d’invocation technique inconnu."""


def ensure_tech_invocations(conn: sqlite3.Connection) -> None:
    """Sème le catalogue. Titre/doc seulement à l’insert.

    Args:
        conn: Canon (commit par l’appelant).
    """
    for ident, etape, kind, path, sha, titre, doc in SEED:
        if kind not in KINDS:
            raise TechError(f'kind technique inconnu : {kind}')
        row = conn.execute(
            'SELECT 1 FROM tech_invocations WHERE id=?', (ident,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE tech_invocations SET etape_id=?, kind=?,'
                ' code_path=?, code_sha=?, enabled=1 WHERE id=?',
                (etape, kind, path, sha, ident),
            )
            continue
        conn.execute(
            'INSERT INTO tech_invocations(id, etape_id, kind, code_path,'
            ' code_sha, titre, doc_md, enabled) VALUES(?,?,?,?,?,?,?,1)',
            (ident, etape, kind, path, sha, titre, doc),
        )


def tech_par_etape(
    conn: sqlite3.Connection, etape_id: str
) -> list[dict[str, Any]]:
    """Invocations techniques d’un sac.

    Args:
        conn: Canon.
        etape_id: Id d’étape.

    Returns:
        Lignes ``{id, kind, titre}``.
    """
    ensure_tech_invocations(conn)
    rows = conn.execute(
        'SELECT id, kind, titre FROM tech_invocations'
        ' WHERE etape_id=? ORDER BY id',
        (etape_id,),
    ).fetchall()
    return [
        {'id': str(r[0]), 'kind': str(r[1]), 'titre': str(r[2])} for r in rows
    ]
