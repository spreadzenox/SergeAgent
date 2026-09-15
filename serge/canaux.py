#!/usr/bin/env python3
"""Canaux d’écriture vers un tiers (pas l’owner)."""

from __future__ import annotations

import sqlite3
from typing import Any

BRIQUE_KINDS = frozenset({'llm', 'tech'})
ETATS = frozenset({'branche', 'prevu'})

# id, titre, doc, path, sha, etat
SEED: tuple[tuple[str, str, str, str, str, str], ...] = (
    (
        'email',
        'E-mail',
        'Sortie texte vers une boîte. Worker ``email.send`` :'
        ' garde-fous, quota, touche, puis Gog ou SMTP.',
        'serge/workers/send.py',
        '5988786aad7b89c7cbab407bf4f4b63836b7d02d6051b5d7c9ac189046a07f16',
        'branche',
    ),
    (
        'voice',
        'Voix',
        'Appel sortant. Worker ``voice.send`` : le broker décide,'
        ' le pont compose. Jamais de dial hors broker.',
        'serge/workers/call.py',
        '4ed728d7eba0b5b61637c877f627b71d146e977f01f511eeeb3f9cb92136701d',
        'branche',
    ),
)

# canal, kind brique, id brique
JONCTIONS: tuple[tuple[str, str, str], ...] = (
    ('email', 'llm', 'fill_slots'),
    ('email', 'llm', 'write_followup'),
    ('email', 'tech', 'sequencer'),
    ('email', 'tech', 'dunning'),
    ('voice', 'llm', 'voice_script'),
    ('voice', 'llm', 'voice_dialog'),
    ('voice', 'tech', 'sequencer'),
)


class CanalError(ValueError):
    """Canal ou jonction invalide."""


def ensure_canaux(conn: sqlite3.Connection) -> None:
    """Sème les canaux. Titre/doc seulement à l’insert.

    Args:
        conn: Canon (commit par l’appelant).
    """
    ids = {row[0] for row in SEED}
    for ident, titre, doc, path, sha, etat in SEED:
        if etat not in ETATS:
            raise CanalError(f'état canal inconnu : {etat}')
        row = conn.execute(
            'SELECT 1 FROM canaux WHERE id=?', (ident,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE canaux SET code_path=?, code_sha=?, etat=? WHERE id=?',
                (path, sha, etat, ident),
            )
            continue
        conn.execute(
            'INSERT INTO canaux(id, titre, doc_md, code_path, code_sha,'
            ' etat) VALUES(?,?,?,?,?,?)',
            (ident, titre, doc, path, sha, etat),
        )
    holes = ','.join('?' * len(ids))
    conn.execute(
        f'DELETE FROM canaux WHERE id NOT IN ({holes})',
        tuple(ids),
    )
    conn.execute('DELETE FROM brique_canaux')
    for canal_id, kind, brique_id in JONCTIONS:
        if canal_id not in ids:
            raise CanalError(f'jonction : canal inconnu {canal_id}')
        if kind not in BRIQUE_KINDS:
            raise CanalError(f'kind brique inconnu : {kind}')
        conn.execute(
            'INSERT INTO brique_canaux(canal_id, brique_kind, brique_id)'
            ' VALUES(?,?,?)',
            (canal_id, kind, brique_id),
        )


def canal_par_id(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une ligne canaux, ou None."""
    ensure_canaux(conn)
    row = conn.execute(
        'SELECT id, titre, doc_md, code_path, code_sha, etat,'
        ' files_sha, updated_at FROM canaux WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return {
        'id': str(row[0]),
        'titre': str(row[1]),
        'doc_md': str(row[2]),
        'code_path': str(row[3] or ''),
        'code_sha': str(row[4] or ''),
        'etat': str(row[5]),
        'files_sha': str(row[6] or ''),
        'updated_at': str(row[7] or ''),
    }


def briques_du_canal(
    conn: sqlite3.Connection, canal_id: str
) -> list[dict[str, str]]:
    """Briques reliées (llm / tech), ordre stable."""
    ensure_canaux(conn)
    rows = conn.execute(
        'SELECT brique_kind, brique_id FROM brique_canaux'
        ' WHERE canal_id=? ORDER BY brique_kind, brique_id',
        (canal_id,),
    ).fetchall()
    return [{'kind': str(r[0]), 'id': str(r[1])} for r in rows]


def canaux_de_brique(
    conn: sqlite3.Connection, kind: str, ident: str
) -> list[dict[str, str]]:
    """Canaux qu’une brique utilise."""
    ensure_canaux(conn)
    rows = conn.execute(
        'SELECT c.id, c.titre FROM brique_canaux j'
        ' JOIN canaux c ON c.id=j.canal_id'
        ' WHERE j.brique_kind=? AND j.brique_id=? ORDER BY c.id',
        (kind, ident),
    ).fetchall()
    return [{'id': str(r[0]), 'titre': str(r[1])} for r in rows]


def canaux_de_etape(
    conn: sqlite3.Connection, etape_id: str
) -> list[dict[str, str]]:
    """Canaux touchés par une invocation de l’étape."""
    ensure_canaux(conn)
    rows = conn.execute(
        'SELECT DISTINCT c.id, c.titre FROM brique_canaux j'
        ' JOIN canaux c ON c.id=j.canal_id'
        " LEFT JOIN llm_points p ON j.brique_kind='llm'"
        ' AND p.id=j.brique_id'
        " LEFT JOIN tech_invocations t ON j.brique_kind='tech'"
        ' AND t.id=j.brique_id'
        ' WHERE p.etape_id=? OR t.etape_id=? ORDER BY c.id',
        (etape_id, etape_id),
    ).fetchall()
    return [{'id': str(r[0]), 'titre': str(r[1])} for r in rows]


def liens_fiche_brique(
    conn: sqlite3.Connection, kind: str, ident: str
) -> list[dict[str, str]]:
    """Liens MC ``type=canal`` pour une fiche brique."""
    return [
        {'type': 'canal', 'id': item['id'], 'titre': item['titre']}
        for item in canaux_de_brique(conn, kind, ident)
    ]


def fiche_canal(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche MC d’un canal.

    Args:
        conn: Canon.
        ident: Id.

    Returns:
        Payload fiche, ou None.
    """
    found = canal_par_id(conn, ident)
    if found is None:
        return None
    liens = []
    for item in briques_du_canal(conn, ident):
        titre = item['id']
        if item['kind'] == 'llm':
            from serge.mc.libelles import titre_llm

            titre = titre_llm(item['id'])
        liens.append({'type': item['kind'], 'id': item['id'], 'titre': titre})
    todo = ''
    if found['etat'] == 'prevu':
        todo = 'Canal déclaré, pas encore un writer runtime.'
    champs = [{'k': 'État', 'v': found['etat']}]
    if found['code_path']:
        champs.append({'k': 'Fichier', 'v': found['code_path']})
    champs.append(
        {'k': 'Dernière modification', 'v': found['updated_at'] or '—'}
    )
    return {
        'type': 'canal',
        'id': found['id'],
        'titre': found['titre'],
        'pourquoi': found['doc_md'],
        'champs': champs,
        'cadres': [
            {
                'titre': 'Briques qui écrivent ici',
                'texte': (
                    'Invocations LLM et techniques reliées.'
                    if liens
                    else 'Aucune brique reliée pour l’instant.'
                ),
                'liens': liens,
            },
            *([{'titre': 'État', 'todo': todo}] if todo else []),
        ],
        'enfants': [],
        'preuve': '',
    }
