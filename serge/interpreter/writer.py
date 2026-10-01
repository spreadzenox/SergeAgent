#!/usr/bin/env python3
"""Écrire la réponse d'une invocation en base, selon ses règles en base.

Un seul code d'écriture sert toutes les invocations. Pour chacune, les
lignes de ``invocation_writes`` disent dans quelle table écrire, si l'on
ajoute, modifie ou supprime, une ligne pour quel élément de la réponse, et
``invocation_write_values`` dit quelle colonne reçoit quoi. Les
protections (``rules.py``) sont appliquées à chaque ligne, et chaque
écriture ou refus est noté au journal.
"""

from __future__ import annotations

import sqlite3
import uuid
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from serge.db.store import append_event, utcnow
from serge.interpreter.rules import (
    cancel_tasks_on_change,
    check_catalogue,
    find_duplicate,
    quota_refusal,
    safe_name,
    table_columns,
    transition_refusal,
)
from serge.interpreter.settings import load_settings, resolve_count


@dataclass
class Written:
    """Les lignes écrites par une règle d'écriture, dans l'ordre."""

    table: str
    for_each: str = ''
    rows: list[dict[str, Any]] = field(default_factory=list)
    # position de l'élément dans la réponse → ligne écrite (ou None si
    # écartée), pour rattacher les écritures filles.
    by_item: dict[tuple[int, ...], dict[str, Any] | None] = field(
        default_factory=dict
    )


def _items(
    answer: Any, path: str
) -> Iterator[tuple[tuple[int, ...], dict[str, Any]]]:
    """Les éléments d'un chemin de liste, avec leur position et leur contexte.

    Exemple : ``fiches.pages`` donne chaque page de chaque fiche ; la
    position ``(1, 0)`` est la première page de la deuxième fiche ; le
    contexte donne accès à la fiche (``fiches``) et à la page
    (``fiches.pages``).
    """
    if not path:
        yield (), {}
        return
    parts = path.split('.')

    def walk(obj: Any, depth: int, pos: tuple[int, ...], ctx: dict[str, Any]):
        if not isinstance(obj, dict):
            return
        values = obj.get(parts[depth])
        if not isinstance(values, list):
            return
        here = '.'.join(parts[: depth + 1])
        for index, item in enumerate(values):
            inner = {**ctx, here: item}
            if depth + 1 == len(parts):
                yield pos + (index,), inner
            else:
                yield from walk(item, depth + 1, pos + (index,), inner)

    yield from walk(answer, 0, (), {})


def _field(answer: Any, ctx: Mapping[str, Any], path: str) -> Any:
    """La valeur d'un champ, vue depuis l'élément en cours."""
    best = ''
    for prefix in ctx:
        if (path == prefix or path.startswith(prefix + '.')) and len(
            prefix
        ) > len(best):
            best = prefix
    value: Any = ctx[best] if best else answer
    rest = path[len(best) + 1 :] if best else path
    for key in [k for k in rest.split('.') if k]:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _values(
    conn: sqlite3.Connection,
    write_id: int,
    answer: Any,
    ctx: Mapping[str, Any],
    task: Mapping[str, str],
    parent_row: Mapping[str, Any] | None,
    settings: Mapping[str, str],
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column, source, value in conn.execute(
        'SELECT column_name, source, value FROM invocation_write_values'
        ' WHERE write_id=?',
        (write_id,),
    ).fetchall():
        if source == 'field':
            out[str(column)] = _field(answer, ctx, str(value))
        elif source == 'fixed':
            out[str(column)] = str(value)
        elif source == 'task':
            out[str(column)] = task.get(str(value), '')
        elif source == 'parent_row':
            out[str(column)] = (parent_row or {}).get(str(value))
        elif source == 'setting':
            out[str(column)] = settings.get(str(value))
        else:
            out[str(column)] = utcnow()
    return out


def _fill_defaults(
    conn: sqlite3.Connection, table: str, values: dict[str, Any]
) -> dict[str, Any]:
    """Ajoute l'identifiant et les dates qu'une ligne nouvelle exige."""
    cols = table_columns(conn, table)
    filled = dict(values)
    id_col = cols.get('id')
    if (
        id_col
        and id_col['pk']
        and 'TEXT' in id_col['type']
        and not filled.get('id')
    ):
        filled['id'] = f'{table[:3]}_{uuid.uuid4().hex[:12]}'
    for stamp in ('created_at', 'updated_at'):
        if stamp in cols and stamp not in filled:
            filled[stamp] = utcnow()
    return filled


def _journal(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    kind: str,
    payload: dict[str, Any],
) -> None:
    row_id = payload.get('id')
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type=f'write.{kind}',
        venture_id=str(payload.get('venture_id') or ''),
        payload={'task': task_id, **payload},
        rows=[(payload['table'], row_id)] if row_id is not None else [],
    )


def _row(
    conn: sqlite3.Connection, table: str, key: str, value: Any
) -> dict | None:
    cursor = conn.execute(
        f'SELECT * FROM "{table}" WHERE "{safe_name(key)}"=?', (value,)
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return {d[0]: row[i] for i, d in enumerate(cursor.description)}


def write_answer(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    task: Mapping[str, str],
    answer: Any,
) -> dict[int, Written]:
    """Écrit la réponse selon les règles de l'invocation.

    Returns:
        Pour chaque règle d'écriture (son id), les lignes écrites.

    Raises:
        WriteConfigError: Une règle vise une table ou colonne interdite.
    """
    results: dict[int, Written] = {}
    settings = load_settings(conn, invocation_id)
    writes = conn.execute(
        'SELECT id, table_name, operation, for_each, parent_write_id,'
        ' key_column, key_source, key_value, max_rows FROM invocation_writes'
        ' WHERE invocation_id=? ORDER BY position',
        (invocation_id,),
    ).fetchall()
    for (
        write_id,
        table,
        operation,
        for_each,
        parent_id,
        key_col,
        key_src,
        key_val,
        max_rows,
    ) in writes:
        table = safe_name(str(table))
        limite = resolve_count(str(max_rows), settings)
        done = Written(table, for_each=str(for_each))
        results[int(write_id)] = done
        parent = results.get(int(parent_id)) if parent_id else None
        for pos, ctx in _items(answer, str(for_each)):
            parent_row = None
            if parent is not None:
                # La ligne mère : celle du même élément si les deux règles
                # parcourent la même liste, sinon celle de l'élément qui
                # contient celui-ci (une fiche, pour ses pages).
                same = parent.for_each == str(for_each)
                parent_row = parent.by_item.get(pos if same else pos[:-1])
                if parent_row is None:
                    continue
            values = _values(
                conn, int(write_id), answer, ctx, task, parent_row, settings
            )
            # Un champ facultatif absent de la réponse n'écrit rien : la
            # colonne garde sa valeur (ou sa valeur par défaut).
            values = {k: v for k, v in values.items() if v is not None}
            check_catalogue(conn, table, str(operation), list(values))
            if limite is not None and len(done.rows) >= limite:
                _journal(
                    conn,
                    invocation_id,
                    task_id,
                    'refused',
                    {
                        'table': table,
                        'reason': f'au plus {limite} ligne(s) par passage',
                        'values': values,
                    },
                )
                done.by_item[pos] = None
                continue
            key = (
                _field(answer, ctx, str(key_val))
                if key_src == 'field'
                else task.get(str(key_val), '')
                if key_src == 'task'
                else str(key_val)
            )
            if operation == 'insert':
                row = _insert(conn, invocation_id, task_id, table, values)
            elif operation == 'delete':
                row = _delete(conn, table, str(key_col), key)
            else:
                row = _update(
                    conn,
                    invocation_id,
                    task_id,
                    table,
                    str(key_col),
                    key,
                    values,
                )
            done.by_item[pos] = row
            if row is not None:
                done.rows.append(row)
        if operation == 'delete' and done.rows:
            ids = [str(r.get('id', '')) for r in done.rows]
            _journal(
                conn,
                invocation_id,
                task_id,
                'deleted',
                {'table': table, 'count': len(ids), 'ids': ids[:50]},
            )
    return results


def _delete(
    conn: sqlite3.Connection, table: str, key_column: str, key: Any
) -> dict[str, Any] | None:
    """Supprime les lignes où ``key_column`` vaut ``key``.

    Rend la première ligne supprimée, pour les écritures qui en dépendent
    (exemple : supprimer un business, puis ses preuves).
    """
    column = safe_name(key_column)
    cursor = conn.execute(
        f'SELECT * FROM "{table}" WHERE "{column}"=?', (key,)
    )
    names = [d[0] for d in cursor.description]
    rows = [dict(zip(names, r, strict=True)) for r in cursor.fetchall()]
    if not rows:
        return None
    conn.execute(f'DELETE FROM "{table}" WHERE "{column}"=?', (key,))
    return rows[0]


def _insert(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    table: str,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    refusal = transition_refusal(conn, table, values, None) or quota_refusal(
        conn, table, values, None
    )
    if refusal:
        _journal(
            conn,
            invocation_id,
            task_id,
            'refused',
            {'table': table, 'reason': refusal},
        )
        return None
    duplicate = find_duplicate(conn, table, values)
    if duplicate is not None:
        rule, existing, action = duplicate
        payload = {
            'table': table,
            'rule': rule,
            'similar_to': existing,
            'values': values,
        }
        _journal(conn, invocation_id, task_id, 'skipped', payload)
        if action == 'refuse':
            raise DuplicateRefused(f'{table} : doublon de {existing} ({rule})')
        return None
    filled = _fill_defaults(conn, table, values)
    columns = [safe_name(c) for c in filled]
    cursor = conn.execute(
        f'INSERT INTO "{table}"({", ".join(columns)})'
        f' VALUES({", ".join("?" for _ in columns)})',
        [filled[c] for c in columns],
    )
    key = 'id' if 'id' in filled else 'rowid'
    row = _row(conn, table, key, filled.get('id', cursor.lastrowid))
    _journal(
        conn,
        invocation_id,
        task_id,
        'inserted',
        {
            'table': table,
            'id': (row or {}).get('id', cursor.lastrowid),
            'values': values,
        },
    )
    return row


def _update(
    conn: sqlite3.Connection,
    invocation_id: str,
    task_id: str,
    table: str,
    key_column: str,
    key: Any,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    current = _row(conn, table, key_column, key)
    if current is None:
        _journal(
            conn,
            invocation_id,
            task_id,
            'refused',
            {
                'table': table,
                'reason': f'aucune ligne où {key_column} = {key}',
            },
        )
        return None
    refusal = transition_refusal(
        conn, table, values, current
    ) or quota_refusal(conn, table, values, current)
    if refusal:
        _journal(
            conn,
            invocation_id,
            task_id,
            'refused',
            {'table': table, 'id': key, 'reason': refusal},
        )
        return None
    changes = dict(values)
    colonnes = table_columns(conn, table)
    if 'updated_at' in colonnes and 'updated_at' not in changes:
        changes['updated_at'] = utcnow()
    # Toutes les lignes visées (une clé comme « status = OPEN » peut en
    # viser plusieurs), pour les règles d'annulation des tâches.
    ids = (
        [
            r[0]
            for r in conn.execute(
                f'SELECT id FROM "{table}" WHERE "{safe_name(key_column)}"=?',
                (key,),
            )
        ]
        if 'id' in colonnes
        else []
    )
    sets = ', '.join(f'"{safe_name(c)}"=?' for c in changes)
    conn.execute(
        f'UPDATE "{table}" SET {sets} WHERE "{safe_name(key_column)}"=?',
        [*changes.values(), key],
    )
    annulees = cancel_tasks_on_change(conn, table, ids, values, utcnow())
    if annulees:
        append_event(
            conn,
            actor=f'invocation:{invocation_id}',
            type='task.cancelled',
            payload={
                'task': task_id,
                'table': table,
                'ids': [str(i) for i in ids],
                'count': annulees,
            },
            rows=[(table, i) for i in ids],
        )
    _journal(
        conn,
        invocation_id,
        task_id,
        'updated',
        {'table': table, 'id': key, 'values': values},
    )
    return _row(conn, table, key_column, key)


class DuplicateRefused(ValueError):
    """Une règle de doublon ``refuse`` a rejeté toute la réponse."""
