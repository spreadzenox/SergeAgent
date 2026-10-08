#!/usr/bin/env python3
"""Le catalogue des canaux : une ligne de ``canaux`` par canal connu.

Un canal est **branché** quand son adaptateur existe dans le code
(``serge/channels/adapters.py``, ``ADAPTERS``) et qu'il est configuré sur
ce serveur : la ligne le dit (``connected``), avec la sorte d'adresse qu'il
utilise et s'il se relève. Sinon il est seulement **prévu** : sa fiche
dans Mission Control dit ce qui manque. Exemple : l'e-mail est prévu sur
une instance sans boîte Gmail ni SMTP/IMAP. Le catalogue est rempli au
démarrage ; la dernière relève (``polled_at``) est gardée.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.channels.adapters import ADAPTERS


def ensure_canaux(conn: sqlite3.Connection) -> None:
    """Remplit le catalogue : un canal par adaptateur du code.

    Le titre et le texte ne sont posés qu'à la création ; l'état, la sorte
    d'adresse et le fait de se relever suivent le code.

    Args:
        conn: Connexion à la base (commit par l'appelant).
    """
    known = {
        a.id: (a.title, a.doc, a.address_channel, a.code_path, a.poll)
        for a in ADAPTERS.values()
    }
    for ident, (titre, doc, address, path, poll) in known.items():
        branche = ADAPTERS[ident].ready()
        values = (
            path,
            'branche' if branche else 'prevu',
            address,
            int(branche),
            int(branche and poll is not None),
        )
        if conn.execute(
            'SELECT 1 FROM canaux WHERE id=?', (ident,)
        ).fetchone():
            conn.execute(
                'UPDATE canaux SET code_path=?, etat=?, address_channel=?,'
                ' connected=?, polls=? WHERE id=?',
                (*values, ident),
            )
            continue
        conn.execute(
            'INSERT INTO canaux(id, titre, doc_md, code_path, etat,'
            ' address_channel, connected, polls) VALUES(?,?,?,?,?,?,?,?)',
            (ident, titre, doc, *values),
        )
    holes = ','.join('?' * len(known))
    conn.execute(f'DELETE FROM canaux WHERE id NOT IN ({holes})', tuple(known))


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


def fiche_canal(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche Mission Control d'un canal.

    Args:
        conn: Connexion à la base.
        ident: Id du canal.

    Returns:
        Contenu de la fiche, ou None.
    """
    found = canal_par_id(conn, ident)
    if found is None:
        return None
    champs = [{'k': 'État', 'v': found['etat']}]
    if found['code_path']:
        champs.append({'k': 'Fichier', 'v': found['code_path']})
    champs.append(
        {'k': 'Dernière modification', 'v': found['updated_at'] or '—'}
    )
    cadres = []
    if found['etat'] == 'prevu':
        cadres.append(
            {
                'titre': 'État',
                'todo': 'Pas branché sur ce serveur : son adaptateur'
                ' n’existe pas encore dans le code (serge/channels/), ou'
                ' le canal n’est pas configuré (pour l’e-mail : une boîte'
                ' Gmail ou SMTP/IMAP dans le fichier d’instance).',
            }
        )
    return {
        'type': 'canal',
        'id': found['id'],
        'titre': found['titre'],
        'pourquoi': found['doc_md'],
        'champs': champs,
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
