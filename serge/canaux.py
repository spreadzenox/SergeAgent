#!/usr/bin/env python3
"""Les canaux par lesquels Serge écrit à un tiers (pas à Julien).

Un canal a sa fiche dans Mission Control. Le code d'envoi existe, mais il
n'est pas encore une capacité du pipeline : il le deviendra au lot 8
(conversations), avec les outils d'envoi et de relève de chaque canal.
"""

from __future__ import annotations

import sqlite3
from typing import Any

ETATS = frozenset({'branche', 'prevu'})

# id, titre, doc, chemin du code, état (l'empreinte est calculée au boot)
SEED: tuple[tuple[str, str, str, str, str], ...] = (
    (
        'email',
        'E-mail',
        'Sortie texte vers une boîte, par Gog ou SMTP, après les'
        ' garde-fous et le quota. Pas encore une capacité du pipeline.',
        'serge/channels/email_smtp.py',
        'prevu',
    ),
    (
        'voice',
        'Voix',
        'Appel sortant : le broker décide, le pont compose. Jamais d’appel'
        ' hors broker. Pas encore une capacité du pipeline.',
        'serge/voice/bridge.py',
        'prevu',
    ),
)


class CanalError(ValueError):
    """Canal invalide."""


def ensure_canaux(conn: sqlite3.Connection) -> None:
    """Pose les canaux. Titre et texte seulement à la création.

    Args:
        conn: Connexion à la base (commit par l'appelant).
    """
    ids = {row[0] for row in SEED}
    for ident, titre, doc, path, etat in SEED:
        if etat not in ETATS:
            raise CanalError(f'état canal inconnu : {etat}')
        row = conn.execute(
            'SELECT 1 FROM canaux WHERE id=?', (ident,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE canaux SET code_path=?, etat=? WHERE id=?',
                (path, etat, ident),
            )
            continue
        conn.execute(
            'INSERT INTO canaux(id, titre, doc_md, code_path,'
            ' etat) VALUES(?,?,?,?,?)',
            (ident, titre, doc, path, etat),
        )
    holes = ','.join('?' * len(ids))
    conn.execute(
        f'DELETE FROM canaux WHERE id NOT IN ({holes})',
        tuple(ids),
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
                'todo': 'Pas encore une capacité du pipeline (lot 8).',
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
