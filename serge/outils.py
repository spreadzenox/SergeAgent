#!/usr/bin/env python3
"""Outils pressables par un jugement (table tools + semence git)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KINDS_OUTIL = frozenset({'deterministe', 'web', 'agent'})


def outil_peut_invoquer(appelant_kind: str, cible_kind: str) -> bool:
    """Seul un non-agent (invocation LLM) enchaîne un tool agent.

    Args:
        appelant_kind: Kind de l’appelant (tool ou ``llm``).
        cible_kind: Kind du tool cible.

    Returns:
        False si un agent appellerait un autre agent.
    """
    return not (appelant_kind == 'agent' and cible_kind == 'agent')


# id, kind, path, sha, titre, doc, etat, montre_partout
# SHA figé : un fichier changé sans maj ici = test rouge.
SEED: tuple[tuple[str, str, str, str, str, str, str, int], ...] = (
    (
        'memory_search',
        'deterministe',
        'serge/memory/search.py',
        '82d43e07949257dc8649c7d273502c9b27139ff277bfde054d4687225c6cb0ce',
        'Chercher dans la mémoire',
        'Un seul outil pour fouiller la mémoire. Si le dossier prévu'
        ' ne suffit pas, le jugement pose une question (« objections'
        ' prix artisans ») et ramène quelques extraits — dans un budget.'
        ' Lecture seule : ça informe, ça n’écrit pas. Certains jugements'
        ' n’y ont pas droit (un appel, un résumé chiffré) : ils restent'
        ' sur le dossier figé.',
        'branche',
        0,
    ),
    (
        'navigateur',
        'web',
        '',
        '',
        'Ouvrir le web (navigateur)',
        'Un vrai navigateur (Brave / Chromium) pour aller voir une'
        ' page, un fil Reddit, un profil. Pas encore branché comme'
        ' outil du jugement. Aujourd’hui Serge ramasse surtout des'
        ' flux RSS. Un budget navigateur existe déjà dans les règles.',
        'prevu',
        1,
    ),
    (
        'demande_capacite',
        'deterministe',
        '',
        '',
        'Demander une nouvelle capacité',
        'Quand Serge ne peut pas (pas de canal, pas d’outil), il'
        ' doit poser un ticket « j’ai besoin de X » plutôt que'
        ' d’inventer. La fiche le montre pour ne pas l’oublier.',
        'prevu',
        1,
    ),
    (
        'agenda',
        'deterministe',
        '',
        '',
        'Agenda',
        'Créneaux et disponibilités. Cité par le dialogue voix.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
    (
        'catalogue',
        'deterministe',
        '',
        '',
        'Catalogue',
        'Prix et offres ownés. Le jugement n’invente pas un montant.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
    (
        'fiches',
        'deterministe',
        '',
        '',
        'Fiches prospect',
        'Fiche de la personne en cours d’appel. Cité par le dialogue voix.'
        ' Pas encore un module runtime.',
        'prevu',
        0,
    ),
)


def ensure_tools(conn: sqlite3.Connection) -> None:
    """Sème les outils. SHA/path/kind depuis git ; titre/doc seulement à l’insert.

    Args:
        conn: Canon (commit par l’appelant).
    """
    for (
        ident,
        kind,
        path,
        sha,
        titre,
        doc,
        etat,
        partout,
    ) in SEED:
        row = conn.execute(
            'SELECT 1 FROM tools WHERE id=?', (ident,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE tools SET kind=?, code_path=?, code_sha=?, etat=?,'
                ' montre_partout=? WHERE id=?',
                (kind, path, sha, etat, partout, ident),
            )
            continue
        conn.execute(
            'INSERT INTO tools(id, kind, code_path, code_sha, titre,'
            ' doc_md, etat, montre_partout) VALUES(?,?,?,?,?,?,?,?)',
            (ident, kind, path, sha, titre, doc, etat, partout),
        )


def outil_par_id(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une ligne tools, ou None.

    Args:
        conn: Canon.
        ident: Id d’outil (``couche5`` → ``memory_search``).

    Returns:
        Dict ou None.
    """
    ensure_tools(conn)
    if ident == 'couche5':
        ident = 'memory_search'
    row = conn.execute(
        'SELECT id, kind, code_path, code_sha, titre, doc_md, etat,'
        ' montre_partout FROM tools WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    return _ligne(row)


def outils_partout(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Outils affichés sur toutes les fiches jugement."""
    ensure_tools(conn)
    rows = conn.execute(
        'SELECT id, kind, code_path, code_sha, titre, doc_md, etat,'
        ' montre_partout FROM tools WHERE montre_partout=1 ORDER BY id'
    ).fetchall()
    return [_ligne(r) for r in rows]


def mtime_fichier(root: Path, rel: str) -> str:
    """Date de modification du fichier, ou vide.

    Args:
        root: Racine repo.
        rel: Chemin relatif.

    Returns:
        ISO UTC, ou ``''``.
    """
    if not rel:
        return ''
    path = root / rel
    if not path.is_file():
        return ''
    stamp = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return stamp.isoformat()


def _ligne(row: Any) -> dict[str, Any]:
    return {
        'id': str(row[0]),
        'kind': str(row[1]),
        'code_path': str(row[2] or ''),
        'code_sha': str(row[3] or ''),
        'titre': str(row[4]),
        'doc_md': str(row[5]),
        'etat': str(row[6]),
        'montre_partout': bool(row[7]),
    }
