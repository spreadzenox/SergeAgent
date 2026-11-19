#!/usr/bin/env python3
"""La fiche d'un compte web de Serge dans Mission Control (``web_accounts``).

Elle dit où en est le compte : son site, son identifiant, s'il a un mot de
passe et une session gardés, les actions faites aujourd'hui sur son
plafond. Le mot de passe et la session ne sont jamais montrés : ils sont
chiffrés en base, et Serge les utilise à la place du modèle.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.web_accounts import actions_today, daily_cap

ETATS = {
    'creating': 'en cours de création',
    'active': 'en service',
    'blocked': 'fermé par le site',
}


def champs_compte(conn: sqlite3.Connection, row: Any) -> list[dict[str, str]]:
    """Ce qu'on montre d'un compte, sans aucun secret."""
    paires = [
        ('Site', row['url']),
        ('Identifiant', row['login'] or '—'),
        ('Nom public', row['handle'] or '—'),
        ('État', ETATS.get(str(row['status']), str(row['status']))),
        ('Mot de passe', 'gardé, chiffré' if row['password_enc'] else 'aucun'),
        (
            'Session',
            f'gardée le {str(row["session_saved_at"])[:16]}'
            if row['session_enc']
            else 'aucune : la prochaine tâche devra se connecter',
        ),
        (
            'Actions aujourd’hui',
            f'{actions_today(conn, str(row["id"]))} sur {daily_cap(conn)}',
        ),
        ('Dernier usage', str(row['last_used_at'])[:16] or 'jamais'),
        ('Sert à la tâche', row['used_by'] or '—'),
        ('Compte rendu', row['note'] or '—'),
    ]
    return [{'k': k, 'v': str(v)} for k, v in paires]


def project_compte(conn: sqlite3.Connection, ident: str) -> dict | None:
    """La fiche d'un compte web."""
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        'SELECT * FROM web_accounts WHERE id=?', (ident,)
    ).fetchone()
    if row is None:
        return None
    return {
        'type': 'compte',
        'id': ident,
        'titre': f'Compte {ident}',
        'pourquoi': (
            'Un compte de Serge sur un site. Une invocation à qui la base'
            ' le donne navigue connectée. Son mot de passe et sa session'
            ' sont chiffrés en base : ni un modèle ni cette page ne les'
            ' voient.'
        ),
        'champs': champs_compte(conn, row),
        'enfants': [{'type': 'plateforme', 'id': ident, 'titre': ident}],
        'preuve': '',
    }
