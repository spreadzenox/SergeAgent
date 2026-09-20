#!/usr/bin/env python3
"""Catalogue des invocations techniques (déterministes, rattachées à une étape)."""

from __future__ import annotations

import sqlite3
from typing import Any

KINDS = frozenset({'cluster', 'select', 'score', 'transform', 'index'})

# id, etape, kind, path, sha, titre, doc
SEED: tuple[tuple[str, str, str, str, str, str, str], ...] = (
    (
        'listen_collect',
        'pre_prospection',
        'transform',
        'serge/listen/collectors.py',
        '',
        'Ramasser des pages',
        'Collecte RSS / pages : déterministe.',
    ),
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
        'metrics_u',
        'prospection_light',
        'score',
        'serge/funnels/metrics.py',
        '',
        'Compteurs U1–U5',
        'Le LLM classe, le code compte.',
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
        'guards_check',
        'prospection_lourde',
        'score',
        'serge/guards/check.py',
        '',
        'Garde-fous',
        'Autoriser / refuser un acte : déterministe.',
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
    (
        'stripe_receive',
        'caisse',
        'transform',
        'serge/collect/receiver.py',
        '',
        'Recevoir Stripe',
        'Webhook → transaction : déterministe.',
    ),
    (
        'dunning',
        'caisse',
        'transform',
        'serge/collect/dunning.py',
        '',
        'Relances d’encaissement',
        'Dunning : templates et règles, 0 LLM.',
    ),
)


class TechError(ValueError):
    """Kind d’invocation technique inconnu."""


def ensure_tech_invocations(conn: sqlite3.Connection) -> None:
    """Sème le catalogue. Titre/doc seulement à l’insert.

    Args:
        conn: Canon (commit par l’appelant).
    """
    ids = {row[0] for row in SEED}
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
    placeholders = ','.join('?' * len(ids))
    conn.execute(
        f'DELETE FROM tech_invocations WHERE id NOT IN ({placeholders})',
        tuple(ids),
    )


def _canaux_tech(conn: sqlite3.Connection, ident: str) -> list[dict[str, str]]:
    from serge.canaux import liens_fiche_brique

    return liens_fiche_brique(conn, 'tech', ident)


def fiche_tech(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche MC d’une invocation technique.

    Args:
        conn: Canon.
        ident: Id.

    Returns:
        Payload fiche, ou None.
    """
    ensure_tech_invocations(conn)
    row = conn.execute(
        'SELECT id, etape_id, kind, code_path, titre, doc_md,'
        ' files_sha, updated_at FROM tech_invocations WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return {
        'type': 'tech',
        'id': str(row[0]),
        'titre': str(row[4]),
        'pourquoi': str(row[5]),
        'champs': [
            {'k': 'Étape', 'v': str(row[1])},
            {'k': 'Kind', 'v': str(row[2])},
            {'k': 'Code', 'v': str(row[3] or '—')},
            {'k': 'Dernière modification', 'v': str(row[7] or '—')},
        ],
        'cadres': [
            {
                'titre': 'Étape',
                'liens': [
                    {
                        'type': 'etape',
                        'id': str(row[1]),
                        'titre': str(row[1]),
                    }
                ],
            },
            {
                'titre': 'Canaux',
                'liens': _canaux_tech(conn, ident),
            },
        ],
        'enfants': [],
        'preuve': '',
    }


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
