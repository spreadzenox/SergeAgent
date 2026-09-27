#!/usr/bin/env python3
"""Fiche Mission Control d'un outil : sa capacité, et ce qu'il lit."""

from __future__ import annotations

import sqlite3
from typing import Any


def _catalogue(conn: sqlite3.Connection, ident: str) -> dict[str, Any]:
    """Ce qu'un outil de lecture a le droit de lire, en clair."""
    from serge.db.query_catalogue import tool_catalogue

    contract = tool_catalogue(conn, ident)
    colonnes = ', '.join(
        f'{c["table"]}.{c["name"]}'
        + (f' (rendue « {c["output_name"]} »)' if c['output_name'] else '')
        for c in contract['columns']
    )
    filtres = ', '.join(
        f'{f["table"]}.{f["column"]} {f["operator"]} '
        + (
            f'« {f["value_text"]} »'
            if f['value_kind'] == 'fixed'
            else f'le paramètre {f["param_name"]}'
        )
        for f in contract['filters']
    )
    jointures = ', '.join(
        f'{j["left_table"]}.{j["left_column"]} ='
        f' {j["right_table"]}.{j["right_column"]}'
        for j in contract['joins']
    )
    return {
        'titre': 'Ce qu’il a le droit de lire',
        'champs': [
            {
                'k': 'Tables',
                'v': ', '.join(t['name'] for t in contract['tables']),
            },
            {'k': 'Colonnes', 'v': colonnes or '—'},
            {'k': 'Toujours filtré par', 'v': filtres or 'rien'},
            {'k': 'Jointures toujours faites', 'v': jointures or 'aucune'},
            {
                'k': 'Paramètres',
                'v': ', '.join(p['name'] for p in contract['params'])
                or 'aucun',
            },
        ],
    }


def project_outil(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """La fiche d'un outil (table ``tools``)."""
    row = conn.execute(
        'SELECT t.id, t.titre, t.doc_md, t.capability_id, t.montre_partout,'
        ' c.title, c.available, c.code_path, c.updated_at FROM tools t'
        ' LEFT JOIN capabilities c ON c.id=t.capability_id WHERE t.id=?',
        (ident,),
    ).fetchone()
    if row is None:
        return None
    champs = [
        {'k': 'Capacité', 'v': str(row[5] or row[3])},
        {
            'k': 'Donné à toutes les invocations',
            'v': 'oui' if row[4] else 'non',
        },
        {'k': 'Fichier de la capacité', 'v': str(row[7] or '—')},
        {'k': 'Code modifié le', 'v': str(row[8] or '—')},
    ]
    cadres: list[dict[str, Any]] = []
    if not row[6]:
        cadres.append(
            {
                'titre': 'État',
                'todo': 'Sa capacité a été retirée du code : l’outil ne'
                ' peut plus tourner.',
            }
        )
    if row[3] == 'db_read':
        cadres.append(_catalogue(conn, ident))
    utilisateurs = [
        {'type': 'llm', 'id': str(r[0]), 'titre': str(r[1] or r[0])}
        for r in conn.execute(
            'SELECT DISTINCT i.id, i.title FROM invocation_tools it'
            ' JOIN invocations i ON i.id=it.invocation_id'
            " WHERE it.tool_id=? AND i.deleted_at='' ORDER BY i.id",
            (ident,),
        ).fetchall()
    ]
    cadres.append(
        {'titre': 'Invocations qui s’en servent', 'liens': utilisateurs}
    )
    return {
        'type': 'outil',
        'id': str(row[0]),
        'titre': str(row[1] or row[0]),
        'pourquoi': str(row[2] or ''),
        'champs': champs,
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
