#!/usr/bin/env python3
"""Exécution des capsules de lecture DB avec paramètres contrôlés."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db.query_builder import execute_db_read, tool_catalogue


def execute_memory_capsule(
    conn: sqlite3.Connection,
    capsule_id: str,
    runtime_params: Mapping[str, Any],
) -> dict[str, Any]:
    """Exécute une capsule avec les paramètres dynamiques de l'ordonnanceur."""
    if not isinstance(runtime_params, Mapping):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'runtime_params objet attendu',
        }
    row = conn.execute(
        'SELECT id, titre, description, prompt_addition, tool_id'
        ' FROM db_readers WHERE id=?',
        (capsule_id,),
    ).fetchone()
    if row is None:
        return {
            'ok': False,
            'code': 'capsule_inconnue',
            'capsule_id': capsule_id,
        }
    fixed = {
        str(item[0]): str(item[1])
        for item in conn.execute(
            'SELECT param_name, value_text FROM db_reader_fixed_params'
            ' WHERE capsule_id=?',
            (capsule_id,),
        ).fetchall()
    }
    fixed_joins = [
        {
            'join_id': str(item[0]),
            'left_table': str(item[1]),
            'left_column': str(item[2]),
            'right_table': str(item[3]),
            'right_column': str(item[4]),
        }
        for item in conn.execute(
            'SELECT join_id, left_table, left_column, right_table, right_column'
            ' FROM db_reader_fixed_joins WHERE capsule_id=?'
            ' ORDER BY position, join_id',
            (capsule_id,),
        ).fetchall()
    ]
    try:
        parameters = {
            str(item['name']): item
            for item in tool_catalogue(conn, str(row[4]))['params']
        }
        typed_fixed: dict[str, Any] = {}
        for name, value in fixed.items():
            parameter = parameters.get(name)
            if parameter is None:
                return {
                    'ok': False,
                    'code': 'invalide',
                    'detail': f'paramètre fixe inconnu: {name}',
                }
            kind = str(parameter['type'])
            if kind == 'integer':
                typed_fixed[name] = int(value)
            elif kind == 'number':
                typed_fixed[name] = float(value)
            elif kind == 'boolean':
                if value not in {'true', 'false'}:
                    raise ValueError(f'booléen fixe invalide: {name}')
                typed_fixed[name] = value == 'true'
            elif kind == 'array':
                raise ValueError(f'array fixe non supporté: {name}')
            else:
                typed_fixed[name] = value
    except (TypeError, ValueError) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
    params = dict(typed_fixed)
    for name, value in runtime_params.items():
        if name in fixed and str(value) != fixed[name]:
            return {
                'ok': False,
                'code': 'parametre_fixe',
                'parametre': str(name),
            }
        params[str(name)] = value
    try:
        result = execute_db_read(
            conn, str(row[4]), params, fixed_joins=fixed_joins
        )
    except (ValueError, sqlite3.Error) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
    return {
        'ok': True,
        'capsule_id': str(row[0]),
        'tool_id': str(row[4]),
        'titre': str(row[1]),
        'description': str(row[2]),
        'prompt_addition': str(row[3]),
        'data': result['data'],
    }
