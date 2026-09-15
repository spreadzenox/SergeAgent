#!/usr/bin/env python3
"""Fiche MC d’un compte web (accounts_standing)."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.comptes import libelle_role, parse_targets


def _champs(paires: list[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{'k': k, 'v': '' if v is None else str(v)} for k, v in paires]


def project_compte(conn: sqlite3.Connection, ident: str) -> dict | None:
    """Fiche d’un compte : santé, crawl, login et mot de passe en clair."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT * FROM accounts_standing WHERE id=?', (ident,)
    ).fetchone()
    if row is None:
        return None
    cibles = parse_targets(str(row['targets_json'] or ''))
    return {
        'type': 'compte',
        'id': ident,
        'titre': f'{row["venue"]} · {row["handle"]}',
        'pourquoi': (
            'Un compte web de Serge. En pause = souvent pour ne pas'
            ' se faire fermer. Login et mot de passe sont en clair :'
            ' Serge a créé ce compte, il n’a pas de valeur hors de lui.'
        ),
        'champs': _champs(
            [
                ('Plateforme', row['venue']),
                ('Identifiant', row['handle']),
                ('Sert à', libelle_role(str(row['role'] or 'ecoute'))),
                ('État', row['status']),
                ('Capital', row['capital']),
                ('Pause jusqu’à', row['cooldown_until'] or '—'),
                ('Profil navigateur', row['profile_path'] or '—'),
                ('Login', row['login'] or '—'),
                ('Mot de passe', row['password'] or '—'),
                ('Nom du secret', row['secret_ref'] or '—'),
                ('Page de connexion', row['login_url'] or '—'),
                ('Cibles', ', '.join(cibles) if cibles else '—'),
                ('Dernière connexion', row['last_login_at'] or 'jamais'),
                ('Dernier ramassage', row['last_fetch_at'] or 'jamais'),
            ]
        ),
        'enfants': [
            {
                'type': 'plateforme',
                'id': row['venue'],
                'titre': row['venue'],
            }
        ],
        'preuve': '',
    }
