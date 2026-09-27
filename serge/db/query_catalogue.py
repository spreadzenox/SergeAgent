#!/usr/bin/env python3
"""Le catalogue d'un outil de lecture : ce qu'il a le droit de lire."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db.query_errors import DbReadError


def tool_catalogue(conn: sqlite3.Connection, tool_id: str) -> dict[str, Any]:
    """Retourne le contrat normalisé d'un tool DB en lecture seule."""
    row = conn.execute(
        'SELECT id, capability_id, titre, doc_md FROM tools WHERE id=?',
        (tool_id,),
    ).fetchone()
    if row is None:
        raise DbReadError(f'tool inconnu: {tool_id}')
    if str(row[1]) != 'db_read':
        raise DbReadError(f'tool non db_read: {tool_id}')
    tables = [
        {'name': str(item[0]), 'position': int(item[1])}
        for item in conn.execute(
            'SELECT table_name, position FROM tool_db_tables'
            ' WHERE tool_id=? ORDER BY position, table_name',
            (tool_id,),
        ).fetchall()
    ]
    columns = [
        {
            'table': str(item[0]),
            'name': str(item[1]),
            'output_name': str(item[2] or ''),
            'position': int(item[3]),
        }
        for item in conn.execute(
            'SELECT table_name, column_name, output_name, position'
            ' FROM tool_db_columns WHERE tool_id=?'
            ' ORDER BY position, table_name, column_name',
            (tool_id,),
        ).fetchall()
    ]
    filters = [
        {
            'id': str(item[0]),
            'table': str(item[1]),
            'column': str(item[2]),
            'operator': str(item[3]),
            'value_kind': str(item[4]),
            'value_text': str(item[5] or ''),
            'param_name': str(item[6] or ''),
        }
        for item in conn.execute(
            'SELECT filter_id, table_name, column_name, operator, value_kind,'
            ' value_text, param_name FROM tool_db_filters'
            ' WHERE tool_id=? ORDER BY position, filter_id',
            (tool_id,),
        ).fetchall()
    ]
    filter_values = {
        str(item['id']): [
            str(value[0])
            for value in conn.execute(
                'SELECT value FROM tool_db_filter_values'
                ' WHERE tool_id=? AND filter_id=? ORDER BY value',
                (tool_id, str(item['id'])),
            ).fetchall()
        ]
        for item in filters
    }
    params = [
        {
            'name': str(item[0]),
            'type': str(item[1]),
            'description': str(item[2] or ''),
            'required': bool(item[3]),
            'default_text': str(item[4] or ''),
        }
        for item in conn.execute(
            'SELECT name, type, description, required, default_text'
            ' FROM tool_db_params WHERE tool_id=? ORDER BY position, name',
            (tool_id,),
        ).fetchall()
    ]
    enums = {
        str(item['name']): [
            str(value[0])
            for value in conn.execute(
                'SELECT value FROM tool_db_param_enums'
                ' WHERE tool_id=? AND param_name=? ORDER BY value',
                (tool_id, str(item['name'])),
            ).fetchall()
        ]
        for item in params
    }
    return {
        'id': str(row[0]),
        'titre': str(row[2] or row[0]),
        'description': str(row[3] or ''),
        'tables': tables,
        'columns': columns,
        'filters': filters,
        'filter_values': filter_values,
        'joins': [
            {
                'join_id': str(item[0]),
                'left_table': str(item[1]),
                'left_column': str(item[2]),
                'right_table': str(item[3]),
                'right_column': str(item[4]),
            }
            for item in conn.execute(
                'SELECT join_id, left_table, left_column, right_table,'
                ' right_column FROM tool_db_joins WHERE tool_id=?'
                ' ORDER BY position, join_id',
                (tool_id,),
            ).fetchall()
        ],
        'params': params,
        'param_enums': enums,
    }


def db_read_tool_ids(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Ids des tools DB individualisés présents dans le catalogue."""
    return tuple(
        str(row[0])
        for row in conn.execute(
            "SELECT id FROM tools WHERE capability_id='db_read' ORDER BY id"
        ).fetchall()
    )


def _rows(data: Mapping[str, Any], key: str) -> list[Mapping[str, Any]]:
    value = data.get(key) or []
    if not isinstance(value, list) or not all(
        isinstance(item, Mapping) for item in value
    ):
        raise DbReadError(f'{key} : une liste d’objets est attendue')
    return value


def _add(conn: sqlite3.Connection, table: str, **values: Any) -> None:
    conn.execute(
        f'INSERT INTO {table}({", ".join(values)})'
        f' VALUES({", ".join("?" for _ in values)})',
        tuple(values.values()),
    )


def seed_read_catalogue(
    conn: sqlite3.Connection, tool_id: str, read: Mapping[str, Any]
) -> None:
    """Ce qu'un outil de lecture a le droit de lire (tables ``tool_db_*``).

    Appelé par le remplissage du pipeline de départ, pour un outil nouveau.
    La première table est celle d'où part la lecture ; les jointures y
    rattachent les autres, et sont toujours appliquées.

    Exemple de ``read`` : ``{tables: [ventures], columns: [{table:
    ventures, name: name, as: title}], filters: [{id: candidats, table:
    ventures, column: lifecycle, fixed: CANDIDATE}]}``.

    Raises:
        DbReadError: Un filtre n'a pas exactement une valeur fixe ou un
            paramètre.
    """
    for position, table in enumerate(read.get('tables') or []):
        _add(
            conn,
            'tool_db_tables',
            tool_id=tool_id,
            table_name=str(table),
            position=position,
        )
    for position, column in enumerate(_rows(read, 'columns')):
        _add(
            conn,
            'tool_db_columns',
            tool_id=tool_id,
            table_name=str(column['table']),
            column_name=str(column['name']),
            output_name=str(column.get('as', '')),
            position=position,
        )
    for position, rule in enumerate(_rows(read, 'filters')):
        if ('fixed' in rule) == ('param' in rule):
            raise DbReadError(
                f'{tool_id}.filters[{position}] : fixed ou param, un seul'
            )
        _add(
            conn,
            'tool_db_filters',
            tool_id=tool_id,
            filter_id=str(rule['id']),
            table_name=str(rule['table']),
            column_name=str(rule['column']),
            operator=str(rule.get('operator', '=')),
            value_kind='fixed' if 'fixed' in rule else 'param',
            value_text=str(rule.get('fixed', '')),
            param_name=str(rule.get('param', '')),
            position=position,
        )
    for position, join in enumerate(_rows(read, 'joins')):
        left_table, _, left_column = str(join['left']).partition('.')
        right_table, _, right_column = str(join['right']).partition('.')
        _add(
            conn,
            'tool_db_joins',
            tool_id=tool_id,
            join_id=str(join['id']),
            left_table=left_table,
            left_column=left_column,
            right_table=right_table,
            right_column=right_column,
            position=position,
        )
    for position, param in enumerate(_rows(read, 'params')):
        _add(
            conn,
            'tool_db_params',
            tool_id=tool_id,
            name=str(param['name']),
            type=str(param.get('type', 'string')),
            description=str(param.get('description', '')),
            required=int(bool(param.get('required', False))),
            default_text=str(param.get('default', '')),
            position=position,
        )
