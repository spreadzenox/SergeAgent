#!/usr/bin/env python3
"""L'empreinte du code derrière un objet : étape, canal ou capacité.

Calculée au démarrage, jamais recopiée à la main. Quand le code d'un objet
change, son empreinte change et sa date ``updated_at`` prend la date du
démarrage : Mission Control affiche ainsi « code modifié le … ».

Les invocations, les outils, les liens et les déclencheurs sont des lignes
en base, pas du code : ils n'ont pas d'empreinte.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path

TABLES = {
    'etape': 'pipeline_steps',
    'canal': 'canaux',
    'capacite': 'capabilities',
}

_FICHIERS_FIXES = {
    'etape': ('serge/etapes.py', 'serge/etape_fiches.py'),
    'canal': ('serge/canaux.py',),
}


def composer(parts: Iterable[str]) -> str:
    """SHA-256 des SHA contenus, triés (pas les chemins, pas les dates)."""
    blob = '\n'.join(sorted(part for part in parts if part))
    return hashlib.sha256(blob.encode()).hexdigest()


def sha256_fichier(path: Path) -> str:
    """SHA-256 hex du contenu seul."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fichiers(kind: str, ident: str, conn: sqlite3.Connection) -> list[str]:
    """Les fichiers (chemins relatifs) qui portent le code de l'objet."""
    rels = list(_FICHIERS_FIXES.get(kind, ()))
    if kind in ('canal', 'capacite'):
        row = conn.execute(
            f'SELECT code_path FROM {TABLES[kind]} WHERE id=?', (ident,)
        ).fetchone()
        path = str(row[0] or '') if row else ''
        if path:
            rels.append(path)
    return rels


def sha_objet(
    root: Path, kind: str, ident: str, conn: sqlite3.Connection
) -> tuple[str, list[str]]:
    """L'empreinte actuelle de l'objet, et les fichiers manquants.

    Args:
        root: Racine du dépôt.
        kind: ``etape``, ``canal`` ou ``capacite``.
        ident: Id de l'objet.
        conn: Connexion à la base (chemins du code).

    Returns:
        ``(sha, erreurs)``.
    """
    erreurs: list[str] = []
    parts: list[str] = []
    for rel in fichiers(kind, ident, conn):
        full = root / rel
        if not full.is_file():
            erreurs.append(f'{kind}.{ident} : fichier manquant ({rel})')
            continue
        parts.append(sha256_fichier(full))
    return composer(parts), erreurs


def poser_shas(conn: sqlite3.Connection, root: Path | None = None) -> None:
    """Calcule au démarrage l'empreinte de chaque objet et la date du changement.

    Exemple : si ``serge/memory/search.py`` change, la capacité
    ``memory_search`` reçoit une nouvelle empreinte et ``updated_at`` prend
    la date du démarrage.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        root: Racine du dépôt (défaut : celle de ce fichier).
    """
    from serge.horloge import iso_utc

    base = root or Path(__file__).resolve().parents[1]
    now = iso_utc()
    for kind, table in TABLES.items():
        for (ident,) in conn.execute(f'SELECT id FROM {table}').fetchall():
            sha, _ = sha_objet(base, kind, str(ident), conn)
            row = conn.execute(
                f'SELECT files_sha FROM {table} WHERE id=?', (ident,)
            ).fetchone()
            if str(row[0] or '') != sha:
                conn.execute(
                    f'UPDATE {table} SET files_sha=?, updated_at=? WHERE id=?',
                    (sha, now, ident),
                )
    for table in ('canaux', 'capabilities'):
        rows = conn.execute(
            f"SELECT id, code_path FROM {table} WHERE code_path!=''"
        ).fetchall()
        for ident, rel in rows:
            full = base / str(rel)
            sha = sha256_fichier(full) if full.is_file() else ''
            conn.execute(
                f'UPDATE {table} SET code_sha=? WHERE id=?', (sha, ident)
            )
