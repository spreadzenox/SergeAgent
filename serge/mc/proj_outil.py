#!/usr/bin/env python3
"""Projection Mission Control d’un tool, y compris les tools DB."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def project_outil(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Une fiche d’outil lue dans ``tools`` et son contrat DB éventuel."""
    from serge.outils import mtime_fichier, outil_par_id

    found = outil_par_id(conn, ident)
    if not found:
        return None
    todo = ''
    if found['etat'] == 'prevu':
        todo = (
            'Pas encore un bouton que l’invocation peut presser toute seule.'
        )
    labels = {
        'deterministe': 'déterministe',
        'agent': 'agent',
        'web': 'web',
        'db_read': 'lecture DB cataloguée',
    }
    champs: list[dict[str, str]] = [
        {'k': 'Genre', 'v': labels.get(found['kind'], found['kind'])}
    ]
    root = Path(__file__).resolve().parents[2]
    if found['code_path']:
        champs.append({'k': 'Fichier', 'v': found['code_path']})
    champs.append(
        {
            'k': 'Dernière modification',
            'v': found.get('updated_at')
            or mtime_fichier(root, found.get('code_path') or '')
            or '—',
        }
    )
    cadres = [{'titre': 'État', 'todo': todo}] if todo else []
    if found['kind'] == 'db_read':
        from serge.db.query_builder import tool_catalogue

        contract = tool_catalogue(conn, ident)
        cadres.append(
            {
                'titre': 'Contrat DB',
                'champs': [
                    {
                        'k': 'Tables',
                        'v': ', '.join(
                            item['name'] for item in contract['tables']
                        ),
                    },
                    {'k': 'Colonnes', 'v': str(len(contract['columns']))},
                    {
                        'k': 'Paramètres',
                        'v': ', '.join(
                            item['name'] for item in contract['params']
                        )
                        or 'aucun',
                    },
                    {
                        'k': 'Jointures paramétrables',
                        'v': ', '.join(
                            item['name'] for item in contract['tables']
                        )
                        or 'aucune',
                    },
                ],
            }
        )
    return {
        'type': 'outil',
        'id': found['id'],
        'titre': found['titre'],
        'pourquoi': found['doc_md'],
        'champs': champs,
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
