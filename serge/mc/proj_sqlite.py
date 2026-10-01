#!/usr/bin/env python3
"""Miroir canon : catalogue des tables + fiche structure."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.schema import SCHEMA_VERSION
from serge.mc.sqlite_catalogue import CATALOGUE

_NOM_TABLE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _meta(nom: str) -> tuple[str, str, str, str]:
    found = CATALOGUE.get(nom)
    if found:
        return found
    return (
        'Table du canon.',
        'Écritures métier.',
        'Lectures MC / workers.',
        'Voir les colonnes ci-dessous.',
    )


def _tables_live(conn: sqlite3.Connection) -> list[str]:
    """Tables réellement présentes (pas la liste figée du schéma)."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
        " AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [str(r[0]) for r in rows if _NOM_TABLE.match(str(r[0]))]


def _lignes(conn: sqlite3.Connection, nom: str) -> int:
    if not _NOM_TABLE.match(nom):
        return 0
    return int(conn.execute(f'SELECT COUNT(*) FROM {nom}').fetchone()[0])


def project_sqlite(
    conn: sqlite3.Connection, ident: str = ''
) -> dict[str, Any]:
    """Catalogue vivant : une ligne par table, compteur à jour."""
    _ = ident
    total = 0
    lignes = []
    noms = _tables_live(conn)
    for nom in noms:
        role, par, vers, _detail = _meta(nom)
        n = _lignes(conn, nom)
        total += n
        lignes.append(
            {
                'id': nom,
                'type': 'table',
                'cellules': [nom, role, par, vers, str(n)],
            }
        )
    return {
        'type': 'sqlite',
        'id': 'canon',
        'titre': 'Canon SQLite',
        'pourquoi': (
            'Une seule vérité. Chaque table est un tiroir du métier :'
            ' qui l’écrit, qui la lit, où ça ressort. Les compteurs'
            ' sont ceux de cette instance, maintenant.'
        ),
        'champs': [
            {'k': 'Tables', 'v': str(len(noms))},
            {'k': 'Lignes', 'v': str(total)},
            {'k': 'Schéma', 'v': f'v{SCHEMA_VERSION}'},
        ],
        'tableau': {
            'titre': 'Tables du canon',
            'colonnes': [
                'Table',
                'Rôle',
                'Remplie par',
                'Sort vers',
                'Lignes',
            ],
            'lignes': lignes,
        },
        'enfants': [],
        'preuve': '',
    }


def project_table(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Structure d’une table : colonnes réelles + explication."""
    if ident not in _tables_live(conn):
        return None
    role, par, vers, detail = _meta(ident)
    cols = conn.execute(f'PRAGMA table_info({ident})').fetchall()
    lignes = []
    for col in cols:
        lignes.append(
            {
                'id': '',
                'type': '',
                'cellules': [
                    str(col[1]),
                    str(col[2] or '—'),
                    'clé primaire' if col[5] else '—',
                ],
            }
        )
    return {
        'type': 'table',
        'id': ident,
        'titre': f'Table {ident}',
        'pourquoi': f'{role} {detail}',
        'champs': [
            {'k': 'Remplie par', 'v': par},
            {'k': 'Sort vers', 'v': vers},
            {'k': 'Lignes maintenant', 'v': str(_lignes(conn, ident))},
            {'k': 'Colonnes', 'v': str(len(cols))},
        ],
        'tableau': {
            'titre': 'Structure',
            'colonnes': ['Colonne', 'Type', 'Clé'],
            'lignes': lignes,
        },
        'cadres': [
            {
                'titre': 'Canon',
                'liens': [
                    {
                        'type': 'sqlite',
                        'id': 'canon',
                        'titre': 'Toutes les tables',
                    }
                ],
            }
        ],
        'enfants': [],
        'preuve': '',
    }
