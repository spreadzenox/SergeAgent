#!/usr/bin/env python3
"""Verrou code ↔ canon : SHA du fichier == code_sha de la semence."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

TABLES_VERROU = ('tools', 'llm_points')


def sha256_fichier(path: Path) -> str:
    """SHA-256 hex du fichier (vérité git)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verifier_verrous(conn: sqlite3.Connection, root: Path) -> list[str]:
    """Écarts semence / disque. Vide = OK.

    Args:
        conn: Canon (lignes déjà semées).
        root: Racine du repo.

    Returns:
        Messages d’écart (fichier manquant ou SHA changé).
    """
    erreurs: list[str] = []
    for table in TABLES_VERROU:
        rows = conn.execute(
            f"SELECT id, code_path, code_sha FROM {table} WHERE code_path!=''"
        ).fetchall()
        for ident, rel, sha in rows:
            full = root / str(rel)
            if not full.is_file():
                erreurs.append(f'{table}.{ident} : fichier manquant ({rel})')
                continue
            got = sha256_fichier(full)
            if got != str(sha):
                erreurs.append(
                    f'{table}.{ident} : fichier modifié sans maj du SHA '
                    f'({rel}). Nouveau : {got}'
                )
    return erreurs
