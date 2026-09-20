#!/usr/bin/env python3
"""Lecture normalisée du catalogue relationnel des tools DB."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.db.query_errors import DbReadError


def tool_catalogue(conn: sqlite3.Connection, tool_id: str) -> dict[str, Any]:
    """Retourne le contrat normalisé d'un tool DB en lecture seule."""
    row = conn.execute(
        'SELECT id, kind, titre, doc_md FROM tools WHERE id=?', (tool_id,)
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
        'joins': [],
        'params': params,
        'param_enums': enums,
    }


def db_read_tool_ids(conn: sqlite3.Connection) -> tuple[str, ...]:
    """Ids des tools DB individualisés présents dans le catalogue."""
    return tuple(
        str(row[0])
        for row in conn.execute(
            "SELECT id FROM tools WHERE kind='db_read' ORDER BY id"
        ).fetchall()
    )
