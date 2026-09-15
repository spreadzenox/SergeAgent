#!/usr/bin/env python3
"""SHA d’un objet catalogue : contenus des fichiers + sous-objets."""

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


def ids_semence() -> set[tuple[str, str]]:
    """Ids que le code déclare (semences), pas encore la base."""
    from serge.canaux import SEED as CANAL_SEED
    from serge.etape_fiches import LIENS
    from serge.etapes import ETAPE_IDS
    from serge.llm_registre import POINT_LOCKS
    from serge.outils import SEED as TOOL_SEED
    from serge.tech_registre import SEED as TECH_SEED

    return (
        {('etape', ident) for ident in ETAPE_IDS}
        | {('llm', ident) for ident in POINT_LOCKS}
        | {('outil', row[0]) for row in TOOL_SEED}
        | {('tech', row[0]) for row in TECH_SEED}
        | {('lien', row[0]) for row in LIENS}
        | {('canal', row[0]) for row in CANAL_SEED}
    )


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


def sha_en_base(conn: sqlite3.Connection, kind: str, ident: str) -> str:
    """``files_sha`` stocké, ou vide."""
    table = TABLES[kind]
    row = conn.execute(
        f'SELECT files_sha FROM {table} WHERE id=?', (ident,)
    ).fetchone()
    return str(row[0] or '') if row else ''


def poser_shas(conn: sqlite3.Connection) -> None:
    """Écrit le SHA figé et la date si le SHA change.

    Args:
        conn: Canon (commit par l’appelant).
    """
    from serge.catalogue_lock import SHA_ATTENDUS
    from serge.horloge import iso_utc

    now = iso_utc()
    for (kind, ident), sha in SHA_ATTENDUS.items():
        table = TABLES[kind]
        row = conn.execute(
            f'SELECT files_sha, updated_at FROM {table} WHERE id=?',
            (ident,),
        ).fetchone()
        if row is None:
            continue
        if str(row[0] or '') != sha:
            conn.execute(
                f'UPDATE {table} SET files_sha=?, updated_at=? WHERE id=?',
                (sha, now, ident),
            )
        elif not str(row[1] or ''):
            conn.execute(
                f'UPDATE {table} SET updated_at=? WHERE id=?',
                (now, ident),
            )


def verifier_objets(conn: sqlite3.Connection, root: Path) -> list[str]:
    """Écarts catalogue : ajout, suppression, SHA fichiers ≠ base.

    Args:
        conn: Canon déjà semé.
        root: Racine du repo.

    Returns:
        Messages (vide = OK).
    """
    from serge.catalogue_lock import SHA_ATTENDUS

    erreurs: list[str] = []
    attendus = set(SHA_ATTENDUS)
    presents = objets_en_base(conn)
    for kind, ident in sorted(presents - attendus):
        erreurs.append(f'objet rajouté : {kind}.{ident}')
    for kind, ident in sorted(attendus - presents):
        erreurs.append(f'objet supprimé : {kind}.{ident}')
    for kind, ident in sorted(attendus & presents):
        actuel, manques = sha_arbre(root, kind, ident, conn)
        erreurs.extend(manques)
        stocke = sha_en_base(conn, kind, ident)
        if actuel != stocke:
            erreurs.append(
                f'{kind}.{ident} : fichiers modifiés (SHA ≠ base).'
                f' Nouveau : {actuel}'
            )
    return erreurs
