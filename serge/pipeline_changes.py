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

Un outil nouveau d'une invocation déjà en base s'ajoute de la même façon,
une seule fois, à la fin de ses outils (un outil retiré ensuite ne revient
pas). De même pour un champ nouveau de sa réponse (``add_outputs``) et une
valeur nouvelle d'une de ses écritures (``add_write_values``, avec le rang
``write`` de l'écriture) :

    changes:
      - id: un_outil_de_plus
        why: L'invocation lit aussi l'e-mail du contact.
        invocation: <l'invocation>
        add_tools:
          - {tool: <l'outil>, mode: given, label: Son e-mail}
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.rules import safe_name, table_columns
from serge.seed_base import PipelineSeedError, seed_tool_link

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
        'policy_sections',
        'policy_settings',
        'serge_texts',
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


def _add_tools(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des outils à une invocation déjà en base ; rend ce qui s'est
    passé, en clair. Un outil déjà lié (même outil, même mode) est gardé."""
    if not isinstance(raw, list) or not all(
        isinstance(tool, Mapping) and tool.get('tool') for tool in raw
    ):
        raise PipelineSeedError('changes : add_tools, une liste d’outils')
    if not conn.execute(
        'SELECT 1 FROM invocations WHERE id=?', (invocation,)
    ).fetchone():
        return 'objet absent'
    parts = []
    for tool in raw:
        tool_id, mode = str(tool['tool']), str(tool.get('mode', 'callable'))
        if conn.execute(
            'SELECT 1 FROM invocation_tools WHERE invocation_id=?'
            ' AND tool_id=? AND mode=?',
            (invocation, tool_id, mode),
        ).fetchone():
            parts.append(f'{tool_id} déjà là')
            continue
        position = conn.execute(
            'SELECT COALESCE(MAX(position) + 1, 0) FROM invocation_tools'
            ' WHERE invocation_id=?',
            (invocation,),
        ).fetchone()[0]
        seed_tool_link(conn, invocation, tool, int(position))
        parts.append(f'{tool_id} ajouté')
    return ' ; '.join(parts)


def _invocation_absente(conn: sqlite3.Connection, invocation: str) -> bool:
    return not conn.execute(
        'SELECT 1 FROM invocations WHERE id=?', (invocation,)
    ).fetchone()


def _add_outputs(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des champs à la réponse d'une invocation déjà en base ; un
    champ déjà là (même chemin) est gardé."""
    if not isinstance(raw, list) or not all(
        isinstance(out, Mapping) and out.get('path') and out.get('type')
        for out in raw
    ):
        raise PipelineSeedError('changes : add_outputs, une liste de champs')
    if _invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for out in raw:
        path = str(out['path'])
        if conn.execute(
            'SELECT 1 FROM invocation_output_fields WHERE invocation_id=?'
            ' AND path=?',
            (invocation, path),
        ).fetchone():
            parts.append(f'{path} déjà là')
            continue
        position = conn.execute(
            'SELECT COALESCE(MAX(position) + 1, 0) FROM'
            ' invocation_output_fields WHERE invocation_id=?',
            (invocation,),
        ).fetchone()[0]
        conn.execute(
            'INSERT INTO invocation_output_fields(invocation_id, path, type,'
            ' choices, required, description, position)'
            ' VALUES(?,?,?,?,?,?,?)',
            (
                invocation,
                path,
                str(out['type']),
                ', '.join(str(c) for c in out.get('choices') or []),
                int(bool(out.get('required', True))),
                str(out.get('description', '')),
                int(position),
            ),
        )
        parts.append(f'{path} ajouté')
    return ' ; '.join(parts)


def _add_write_values(
    conn: sqlite3.Connection, invocation: str, write: Any, raw: Any
) -> str:
    """Ajoute des valeurs à une écriture d'une invocation déjà en base
    (son rang ``write`` dans ``writes``) ; une colonne déjà écrite est
    gardée."""
    if not isinstance(raw, Mapping) or not isinstance(write, int):
        raise PipelineSeedError(
            'changes : add_write_values, un rang write et des valeurs'
        )
    if _invocation_absente(conn, invocation):
        return 'objet absent'
    row = conn.execute(
        'SELECT id FROM invocation_writes WHERE invocation_id=? AND position=?',
        (invocation, write),
    ).fetchone()
    if row is None:
        return 'écriture absente'
    parts = []
    for column, spec in raw.items():
        if not isinstance(spec, Mapping):
            raise PipelineSeedError(f'changes : valeur de {column} mal écrite')
        if conn.execute(
            'SELECT 1 FROM invocation_write_values WHERE write_id=?'
            ' AND column_name=?',
            (row[0], str(column)),
        ).fetchone():
            parts.append(f'{column} déjà là')
            continue
        conn.execute(
            'INSERT INTO invocation_write_values(write_id, column_name,'
            ' source, value) VALUES(?,?,?,?)',
            (
                row[0],
                str(column),
                str(spec['source']),
                str(spec.get('value', '')),
            ),
        )
        parts.append(f'{column} ajouté')
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
        invocation = str(change.get('invocation') or '')
        if 'add_tools' in change:
            result = _add_tools(conn, invocation, change['add_tools'])
        elif 'add_outputs' in change:
            result = _add_outputs(conn, invocation, change['add_outputs'])
        elif 'add_write_values' in change:
            result = _add_write_values(
                conn,
                invocation,
                change.get('write'),
                change['add_write_values'],
            )
        else:
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
            result = _result(conn, table, where, sets)
        conn.execute(
            'INSERT INTO pipeline_changes(id, applied_at, result)'
            ' VALUES(?,?,?)',
            (ident, iso_utc(), result),
        )
