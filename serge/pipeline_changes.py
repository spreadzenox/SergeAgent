#!/usr/bin/env python3
"""Modifier un objet déjà en base, une seule fois, sans écraser Julien.

``config/pipeline.yaml`` n'écrase jamais un objet déjà en base. Quand il
faut changer une valeur d'un objet qui existe déjà sur les instances (par
exemple les tours d'outils d'une invocation, de 25 à 10), on l'écrit dans
la section ``changes`` du fichier :

    changes:
      - id: moins_de_tours
        why: Avec plusieurs outils par tour, 10 tours suffisent.
        table: invocations
        where: {id: <l'invocation>}
        set: {max_tool_turns: {from: 25, to: 10}}

Chaque modification est appliquée une seule fois par instance, et
seulement si la valeur en base est encore celle d'origine (``from``) : une
valeur changée dans Mission Control est gardée. Le résultat est noté dans
``pipeline_changes`` (visible dans Mission Control, page SQLite).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.rules import safe_name, table_columns
from serge.seed_base import PipelineSeedError

# Les tables du pipeline qu'une modification peut viser.
TABLES = frozenset(
    {
        'invocations',
        'invocation_tools',
        'invocation_settings',
        'links',
        'triggers',
        'table_quotas',
        'table_views',
        'table_view_columns',
        'llm_models',
    }
)


def _result(
    conn: sqlite3.Connection,
    table: str,
    where: Mapping[str, Any],
    changes: Mapping[str, Any],
) -> str:
    """Applique une modification ; rend ce qui s'est passé, en clair."""
    columns = table_columns(conn, table)
    for name in [*where, *changes]:
        if safe_name(str(name)) not in columns:
            raise PipelineSeedError(
                f'changes : colonne absente {table}.{name}'
            )
    clause = ' AND '.join(f'"{name}"=?' for name in where)
    rows = conn.execute(
        f'SELECT rowid, * FROM "{table}" WHERE {clause}',
        [str(v) for v in where.values()],
    ).fetchall()
    if not rows:
        return 'objet absent'
    if len(rows) > 1:
        raise PipelineSeedError(f'changes : plusieurs lignes dans {table}')
    names = ['rowid', *columns]
    current = dict(zip(names, rows[0], strict=True))
    parts = []
    for name, spec in changes.items():
        # Un texte (un prompt) se compare sans ses blancs de fin, comme il
        # est rangé en base.
        before, after = str(spec['from']).strip(), str(spec['to']).strip()
        now = str(current[name] if current[name] is not None else '').strip()
        if now == after:
            parts.append(f'{name} déjà à jour')
        elif now != before:
            parts.append(f'{name} gardé (changé dans Mission Control)')
        else:
            conn.execute(
                f'UPDATE "{table}" SET "{name}"=? WHERE rowid=?',
                (after, current['rowid']),
            )
            parts.append(
                f'{name} modifié'
                if '\n' in after
                else f'{name} : {before or "(vide)"} → {after}'
            )
    return ' ; '.join(parts)


def apply_changes(conn: sqlite3.Connection, raw: Any) -> None:
    """Applique les modifications de ``pipeline.yaml`` pas encore passées.

    Raises:
        PipelineSeedError: Modification mal écrite (table ou colonne
            inconnue, objet visé par plusieurs lignes).
    """
    from serge.horloge import iso_utc

    for change in raw or []:
        ident = str(change['id'])
        if conn.execute(
            'SELECT 1 FROM pipeline_changes WHERE id=?', (ident,)
        ).fetchone():
            continue
        table = str(change['table'])
        if table not in TABLES:
            raise PipelineSeedError(
                f'changes.{ident} : table {table} interdite'
            )
        where, sets = change.get('where'), change.get('set')
        if not isinstance(where, Mapping) or not where:
            raise PipelineSeedError(f'changes.{ident} : where manquant')
        if not isinstance(sets, Mapping) or not sets:
            raise PipelineSeedError(f'changes.{ident} : set manquant')
        conn.execute(
            'INSERT INTO pipeline_changes(id, applied_at, result)'
            ' VALUES(?,?,?)',
            (ident, iso_utc(), _result(conn, table, where, sets)),
        )
