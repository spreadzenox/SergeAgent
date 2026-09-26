#!/usr/bin/env python3
"""Empreinte d’un objet catalogue : contenus des fichiers + sous-objets.

Calculée au démarrage, jamais recopiée à la main.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Iterable
from pathlib import Path

KINDS = ('etape', 'llm', 'tech', 'outil', 'lien', 'canal')

TABLES = {
    'etape': 'pipeline_steps',
    'llm': 'llm_points',
    'tech': 'tech_invocations',
    'outil': 'tools',
    'lien': 'etape_liens',
    'canal': 'canaux',
}

_FICHIERS_FIXES = {
    'etape': ('serge/etapes.py', 'serge/etape_fiches.py'),
    'lien': ('serge/etape_fiches.py',),
    'llm': ('config/llm-points.yaml',),
    'canal': ('serge/canaux.py',),
}


def composer(parts: Iterable[str]) -> str:
    """SHA-256 des SHA contenus, triés (pas les chemins, pas les dates)."""
    blob = '\n'.join(sorted(part for part in parts if part))
    return hashlib.sha256(blob.encode()).hexdigest()


def sha256_fichier(path: Path) -> str:
    """SHA-256 hex du contenu seul."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def objets_en_base(conn: sqlite3.Connection) -> set[tuple[str, str]]:
    """Objets catalogue présents (kind, id)."""
    out: set[tuple[str, str]] = set()
    for kind, table in TABLES.items():
        rows = conn.execute(f'SELECT id FROM {table}').fetchall()
        out.update((kind, str(row[0])) for row in rows)
    return out


def fichiers(kind: str, ident: str, conn: sqlite3.Connection) -> list[str]:
    """Chemins relatifs qui encodent l’objet (hors sous-objets)."""
    rels = list(_FICHIERS_FIXES.get(kind, ()))
    table = TABLES.get(kind)
    if table in ('llm_points', 'tech_invocations', 'tools', 'canaux'):
        row = conn.execute(
            f'SELECT code_path FROM {table} WHERE id=?', (ident,)
        ).fetchone()
        path = str(row[0] or '') if row else ''
        if path:
            rels.append(path)
    return rels


def enfants(
    kind: str, ident: str, conn: sqlite3.Connection
) -> list[tuple[str, str]]:
    """Sous-objets (kind, id), ordre stable."""
    if kind == 'etape':
        llms = conn.execute(
            'SELECT id FROM llm_points WHERE etape_id=? ORDER BY id',
            (ident,),
        ).fetchall()
        techs = conn.execute(
            'SELECT id FROM tech_invocations WHERE etape_id=? ORDER BY id',
            (ident,),
        ).fetchall()
        return [('llm', str(r[0])) for r in llms] + [
            ('tech', str(r[0])) for r in techs
        ]
    if kind == 'llm':
        rows = conn.execute(
            'SELECT tool_id FROM llm_point_tools WHERE point_id=? ORDER BY tool_id',
            (ident,),
        ).fetchall()
        return [('outil', str(r[0])) for r in rows]
    return []


def sha_arbre(
    root: Path, kind: str, ident: str, conn: sqlite3.Connection
) -> tuple[str, list[str]]:
    """SHA actuel (fichiers + enfants) et écarts (fichier manquant).

    Args:
        root: Racine du repo.
        kind: ``etape`` / ``llm`` / ``tech`` / ``outil`` / ``lien`` / ``canal``.
        ident: Id d’objet.
        conn: Canon (chemins et jonctions).

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
    for child_kind, child_id in enfants(kind, ident, conn):
        child_sha, child_err = sha_arbre(root, child_kind, child_id, conn)
        erreurs.extend(child_err)
        parts.append(child_sha)
    return composer(parts), erreurs


def poser_shas(conn: sqlite3.Connection, root: Path | None = None) -> None:
    """Calcule au boot l’empreinte de chaque objet et la date du changement.

    Exemple : si ``serge/memory/search.py`` change, l’outil
    ``memory_search`` reçoit une nouvelle empreinte et ``updated_at`` prend
    la date du boot. Mission Control peut ainsi afficher « code modifié le … ».

    Args:
        conn: Canon (commit par l’appelant).
        root: Racine du dépôt (défaut : celle de ce fichier).
    """
    from serge.horloge import iso_utc

    base = root or Path(__file__).resolve().parents[1]
    now = iso_utc()
    for kind, table in TABLES.items():
        for (ident,) in conn.execute(f'SELECT id FROM {table}').fetchall():
            sha, _ = sha_arbre(base, kind, str(ident), conn)
            row = conn.execute(
                f'SELECT files_sha FROM {table} WHERE id=?', (ident,)
            ).fetchone()
            if str(row[0] or '') != sha:
                conn.execute(
                    f'UPDATE {table} SET files_sha=?, updated_at=? WHERE id=?',
                    (sha, now, ident),
                )
    for table in ('tools', 'llm_points', 'tech_invocations', 'canaux'):
        rows = conn.execute(
            f"SELECT id, code_path FROM {table} WHERE code_path!=''"
        ).fetchall()
        for ident, rel in rows:
            full = base / str(rel)
            sha = sha256_fichier(full) if full.is_file() else ''
            conn.execute(
                f'UPDATE {table} SET code_sha=? WHERE id=?', (sha, ident)
            )
