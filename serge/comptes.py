#!/usr/bin/env python3
"""Comptes web de Serge : colonnes d’identité + crawl (pas les secrets)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

ROLES = frozenset({'ecoute', 'publication', 'les_deux'})

ROLE_LIBELLES = {
    'ecoute': 'Écouter',
    'publication': 'Publier',
    'les_deux': 'Écouter et publier',
}

# name, SQL type+default (ALTER et CREATE).
COLONNES = (
    ('role', "TEXT NOT NULL DEFAULT 'ecoute'"),
    ('profile_path', "TEXT NOT NULL DEFAULT ''"),
    ('secret_ref', "TEXT NOT NULL DEFAULT ''"),
    ('login_url', "TEXT NOT NULL DEFAULT ''"),
    ('targets_json', "TEXT NOT NULL DEFAULT '[]'"),
    ('last_login_at', "TEXT NOT NULL DEFAULT ''"),
    ('last_fetch_at', "TEXT NOT NULL DEFAULT ''"),
)


class CompteError(ValueError):
    """Rôle ou cibles invalides."""


def libelle_role(role: str) -> str:
    """Libellé FR d’un rôle (inconnu → la clé brute)."""
    return ROLE_LIBELLES.get(role, role)


def parse_targets(raw: str) -> list[str]:
    """Liste d’URLs / sous-forums depuis le JSON stocké."""
    try:
        data = json.loads(raw or '[]')
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item).strip() for item in data if str(item).strip()]


def ensure_account_columns(conn: sqlite3.Connection) -> None:
    """Ajoute les colonnes crawl si la table est une vieille version.

    Args:
        conn: Canon (commit par l’appelant).
    """
    have = {
        str(row[1])
        for row in conn.execute('PRAGMA table_info(accounts_standing)')
    }
    for name, decl in COLONNES:
        if name not in have:
            conn.execute(
                f'ALTER TABLE accounts_standing ADD COLUMN {name} {decl}'
            )


def assert_role(role: str) -> str:
    """Valide un rôle. Lève CompteError sinon."""
    if role not in ROLES:
        raise CompteError(f'rôle inconnu : {role}')
    return role


def dump_targets(items: list[Any]) -> str:
    """Sérialise des cibles (URLs) en JSON."""
    cleaned = [str(item).strip() for item in items if str(item).strip()]
    return json.dumps(cleaned, ensure_ascii=False)
