#!/usr/bin/env python3
"""Comptes web de Serge : writer standing + colonnes (login en clair)."""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from serge.horloge import iso_utc

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
    ('login', "TEXT NOT NULL DEFAULT ''"),
    ('password', "TEXT NOT NULL DEFAULT ''"),
)


class CompteError(ValueError):
    """Lieu, login, mot de passe ou rôle invalide."""


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
    """Ajoute les colonnes crawl / login si la table est une vieille version.

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


def _new_id() -> str:
    return f's_{uuid.uuid4().hex[:12]}'


def enregistrer_compte(
    conn: sqlite3.Connection,
    venue: str,
    handle: str,
    login: str,
    password: str,
    *,
    role: str | None = None,
    login_url: str = '',
    targets: list[Any] | None = None,
    profile_path: str = '',
) -> str:
    """Crée ou met à jour le compte de ce lieu. Login et mot de passe en clair.

    Args:
        conn: Canon (commit par l’appelant).
        venue: Lieu (``reddit``, ``linkedin``, ``gmail``…).
        handle: Identifiant public sur ce lieu.
        login: Identifiant de connexion (souvent l’e-mail).
        password: Mot de passe, en clair.
        role: ``ecoute``, ``publication`` ou ``les_deux`` (défaut à la
            création : ``ecoute`` ; à la mise à jour : inchangé).
        login_url: Page de connexion, si on la connaît.
        targets: URLs ou sous-forums à crawler.
        profile_path: Dossier de session navigateur, s’il existe déjà.

    Returns:
        Id du compte (créé ou déjà là).

    Raises:
        CompteError: Lieu, handle, login ou mot de passe vide ; rôle inconnu.
    """
    lieu = venue.strip()
    public = handle.strip()
    identifiant = login.strip()
    secret = password.strip()
    if not lieu or not public or not identifiant or not secret:
        raise CompteError('lieu, identifiant, login et mot de passe requis')
    row = conn.execute(
        'SELECT id, profile_path, login_url, targets_json, role'
        ' FROM accounts_standing WHERE venue=? AND handle=?',
        (lieu, public),
    ).fetchone()
    maintenant = iso_utc()
    if row is None:
        ident = _new_id()
        conn.execute(
            'INSERT INTO accounts_standing('
            'id, venue, handle, capital, age_days, warnings, status,'
            ' cooldown_until, updated_at, role, profile_path, secret_ref,'
            ' login_url, targets_json, last_login_at, last_fetch_at,'
            ' login, password) VALUES('
            "?,?,?,1.0,0,0,'active','',?,?,?,'',?,?,?,?,?,?)",
            (
                ident,
                lieu,
                public,
                maintenant,
                assert_role(role or 'ecoute'),
                profile_path.strip(),
                login_url.strip(),
                dump_targets(targets or []),
                '',
                '',
                identifiant,
                secret,
            ),
        )
        return ident
    ident = str(row[0])
    conn.execute(
        'UPDATE accounts_standing SET login=?, password=?, role=?,'
        ' login_url=?, targets_json=?, profile_path=?, updated_at=?'
        ' WHERE id=?',
        (
            identifiant,
            secret,
            assert_role(role) if role is not None else str(row[4]),
            login_url.strip() or str(row[2] or ''),
            (
                dump_targets(targets)
                if targets is not None
                else str(row[3] or '[]')
            ),
            profile_path.strip() or str(row[1] or ''),
            maintenant,
            ident,
        ),
    )
    return ident
