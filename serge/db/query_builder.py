#!/usr/bin/env python3
"""Query builder fermé pour les tools ``kind='db_read'``.

Les identifiants SQL viennent exclusivement du catalogue relationnel du tool.
Les valeurs venant du modèle ou de l'ordonnanceur restent des paramètres
SQLite, après validation du contrat déclaré.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from serge.db.query_catalogue import (  # noqa: F401
    db_read_tool_ids,
    tool_catalogue,
)
from serge.db.query_errors import DbReadError

_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_OPERATORS = frozenset({'=', '!=', '<', '<=', '>', '>=', 'LIKE', 'IN'})
_PARAM_TYPES = frozenset({'string', 'integer', 'number', 'boolean', 'array'})
_MAX_ROWS = 500


def _quote(identifier: str) -> str:
    if not _IDENTIFIER.fullmatch(identifier) or identifier.startswith(
        'sqlite_'
    ):
        raise DbReadError(f'identifiant SQL interdit: {identifier!r}')
    return f'"{identifier}"'


def _real_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    _quote(table)
    if (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
        is None
    ):
        raise DbReadError(f'table absente du canon: {table}')
    return {
        str(row[1])
        for row in conn.execute(f'PRAGMA table_info({_quote(table)})')
    }


def _validate_catalogue(
    conn: sqlite3.Connection, catalogue: Mapping[str, Any]
) -> tuple[set[str], set[str]]:
    tables = {str(item['name']) for item in catalogue['tables']}
    columns = {
        f'{item["table"]}.{item["name"]}' for item in catalogue['columns']
    }
    if not tables or not columns:
        raise DbReadError(f'tool sans tables/colonnes: {catalogue["id"]}')
    for table in tables:
        if not _IDENTIFIER.fullmatch(table) or table.startswith('sqlite_'):
            raise DbReadError(f'table de catalogue interdite: {table!r}')
        actual = _real_columns(conn, table)
        configured = {
            str(item['name'])
            for item in catalogue['columns']
            if str(item['table']) == table
        }
        if not configured <= actual:
            raise DbReadError(f'colonne absente du canon: {table}')
    for column in columns:
        table, name = column.split('.', 1)
        if table not in tables:
            raise DbReadError(f'colonne hors table de catalogue: {column!r}')
        if not _IDENTIFIER.fullmatch(name):
            raise DbReadError(f'colonne de catalogue interdite: {column!r}')
    for item in catalogue['filters']:
        if item['operator'] not in _OPERATORS:
            raise DbReadError(f'opérateur interdit: {item["operator"]}')
        if (
            item['table'] not in tables
            or f'{item["table"]}.{item["column"]}' not in columns
        ):
            raise DbReadError(f'filtre hors catalogue: {item["id"]}')
    param_names = {str(item['name']) for item in catalogue['params']}
    for item in catalogue['params']:
        if item['type'] not in _PARAM_TYPES:
            raise DbReadError(f'type de paramètre interdit: {item["type"]}')
    for item in catalogue['filters']:
        if (
            item['value_kind'] == 'param'
            and item['param_name'] not in param_names
        ):
            raise DbReadError(
                f'paramètre de filtre inconnu: {item["param_name"]}'
            )
        if item['value_kind'] == 'enum':
            if item['param_name'] and item['param_name'] not in param_names:
                raise DbReadError(f'enum sans paramètre: {item["id"]}')
            if not item['param_name'] and not item['value_text']:
                raise DbReadError(f'enum sans valeur: {item["id"]}')
            if not catalogue['filter_values'].get(item['id']):
                raise DbReadError(f'enum vide: {item["id"]}')
    return tables, columns


def _parameters(
    catalogue: Mapping[str, Any], arguments: Mapping[str, Any]
) -> dict[str, Any]:
    from serge.db.query_values import coerce, default

    declared = {str(item['name']): item for item in catalogue['params']}
    special = {'columns', 'joins'}
    unknown = set(arguments) - set(declared) - special
    if unknown:
        raise DbReadError(f'paramètre non déclaré: {sorted(unknown)[0]}')
    values: dict[str, Any] = {}
    for name, parameter in declared.items():
        if name in arguments:
            value = coerce(arguments[name], parameter)
        else:
            value = default(parameter)
            if value is None and bool(parameter['required']):
                raise DbReadError(f'paramètre requis absent: {name}')
            if value is not None:
                value = coerce(value, parameter)
        enum = catalogue['param_enums'].get(name) or []
        if enum:
            candidates = value if isinstance(value, list) else [value]
            if any(item not in enum for item in candidates):
                raise DbReadError(f'valeur hors enum: {name}')
        values[name] = value
    for item in catalogue['filters']:
        if (
            item['value_kind'] in {'param', 'enum'}
            and item['param_name']
            and values.get(item['param_name']) is None
        ):
            raise DbReadError(
                f'paramètre de filtre absent: {item["param_name"]}'
            )
    return values


def _normalise_join(
    catalogue: Mapping[str, Any], item: Any, *, allow_id: bool
) -> dict[str, str]:
    if not isinstance(item, Mapping):
        raise DbReadError('jointure objet attendue')
    required = {'left_table', 'left_column', 'right_table', 'right_column'}
    allowed = required | ({'join_id'} if allow_id else set())
    unknown = set(item) - allowed
    if unknown:
        raise DbReadError(
            f'propriété de jointure inconnue: {sorted(unknown)[0]}'
        )
    tables = {str(entry['name']) for entry in catalogue['tables']}
    columns = {
        f'{entry["table"]}.{entry["name"]}' for entry in catalogue['columns']
    }
    values: dict[str, str] = {}
    for side in ('left', 'right'):
        table = item.get(f'{side}_table')
        column = item.get(f'{side}_column')
        if not isinstance(table, str) or table not in tables:
            raise DbReadError(f'table de jointure non autorisée: {table!r}')
        if not isinstance(column, str):
            raise DbReadError('colonne de jointure invalide')
        qualified = f'{table}.{column}'
        if qualified not in columns and column.startswith(f'{table}.'):
            column = column[len(table) + 1 :]
            qualified = f'{table}.{column}'
        if qualified not in columns:
            raise DbReadError(
                f'colonne de jointure non autorisée: {qualified}'
            )
        values[f'{side}_table'] = table
        values[f'{side}_column'] = column
    if values['left_table'] == values['right_table']:
        raise DbReadError('jointure sur une seule table')
    if allow_id:
        join_id = item.get('join_id') or item.get('id')
        if not isinstance(join_id, str) or not join_id:
            raise DbReadError('identifiant de jointure fixe manquant')
        values['id'] = join_id
    else:
        values['id'] = 'dynamic'
    return values


def _join_items(
    catalogue: Mapping[str, Any],
    requested: Any,
    fixed_joins: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if requested is None:
        requested = []
    if not isinstance(requested, list):
        raise DbReadError('joins doit être une liste')
    result: list[Mapping[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in fixed_joins:
        found = _normalise_join(catalogue, item, allow_id=True)
        key = (
            found['left_table'],
            found['left_column'],
            found['right_table'],
            found['right_column'],
        )
        if key in seen:
            raise DbReadError('jointure fixe dupliquée')
        seen.add(key)
        result.append(found)
    for item in requested:
        found = _normalise_join(catalogue, item, allow_id=False)
        key = (
            found['left_table'],
            found['left_column'],
            found['right_table'],
            found['right_column'],
        )
        if key in seen:
            raise DbReadError('jointure dupliquée')
        seen.add(key)
        result.append(found)
    return result


def _join_path(
    catalogue: Mapping[str, Any], joins: Sequence[Mapping[str, Any]]
) -> tuple[set[str], list[str]]:
    root = str(catalogue['tables'][0]['name'])
    included = {root}
    remaining = list(joins)
    join_sql: list[str] = []
    while remaining:
        progress = False
        for index, join in enumerate(remaining):
            left = str(join['left_table'])
            right = str(join['right_table'])
            if left in included and right not in included:
                target = right
            elif right in included and left not in included:
                target = left
            else:
                continue
            on = (
                f'{_quote(left)}.{_quote(join["left_column"])} = '
                f'{_quote(right)}.{_quote(join["right_column"])}'
            )
            join_sql.append(f' JOIN {_quote(target)} ON {on}')
            included.add(target)
            remaining.pop(index)
            progress = True
            break
        if not progress:
            raise DbReadError(
                'jointures ne forment pas un chemin depuis la racine'
            )
    return included, join_sql


def _columns(
    catalogue: Mapping[str, Any], requested: Any, joined: set[str]
) -> list[Mapping[str, Any]]:
    allowed = list(catalogue['columns'])
    if requested is None:
        result = [item for item in allowed if item['table'] in joined]
    elif isinstance(requested, list):
        result = []
        for name in requested:
            found = next(
                (
                    item
                    for item in allowed
                    if name == f'{item["table"]}.{item["name"]}'
                ),
                None,
            )
            if found is None:
                raise DbReadError(f'colonne non autorisée: {name}')
            if found['table'] not in joined:
                raise DbReadError(f'colonne sans jointure: {name}')
            result.append(found)
    else:
        raise DbReadError('columns doit être une liste')
    if not result:
        raise DbReadError('columns vide')
    return result


def _where(
    catalogue: Mapping[str, Any], values: Mapping[str, Any], included: set[str]
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    bound: list[Any] = []
    for item in catalogue['filters']:
        if item['table'] not in included:
            raise DbReadError(f'filtre sans table: {item["id"]}')
        kind = item['value_kind']
        if kind == 'fixed':
            value: Any = item['value_text']
        elif kind == 'param':
            value = values.get(item['param_name'])
        elif kind == 'enum':
            value = (
                values.get(item['param_name'])
                if item['param_name']
                else item['value_text']
            )
            if value not in catalogue['filter_values'][item['id']]:
                raise DbReadError(f'valeur hors filtre enum: {item["id"]}')
        else:
            raise DbReadError(f'source de filtre interdite: {kind}')
        operator = item['operator']
        column = f'{_quote(item["table"])}.{_quote(item["column"])}'
        if operator == 'IN':
            if not isinstance(value, list) or not value:
                raise DbReadError(
                    f'IN doit recevoir une liste non vide: {item["id"]}'
                )
            clauses.append(f'{column} IN ({", ".join("?" for _ in value)})')
            bound.extend(value)
        else:
            clauses.append(f'{column} {operator} ?')
            bound.append(value)
    return clauses, bound


def build_db_read_query(
    conn: sqlite3.Connection,
    tool_id: str,
    arguments: Mapping[str, Any],
    *,
    fixed_joins: Sequence[Mapping[str, Any]] = (),
) -> tuple[str, list[Any], list[str]]:
    """Construit une requête bornée à un contrat DB, sans l'exécuter."""
    if not isinstance(arguments, Mapping):
        raise DbReadError('arguments objet attendus')
    catalogue = tool_catalogue(conn, tool_id)
    tables, _columns_set = _validate_catalogue(conn, catalogue)
    values = _parameters(catalogue, arguments)
    joins = _join_items(catalogue, arguments.get('joins'), fixed_joins)
    included, join_sql = _join_path(catalogue, joins)
    root = str(catalogue['tables'][0]['name'])
    selected = _columns(catalogue, arguments.get('columns'), included)
    aliases: list[str] = []
    select_sql: list[str] = []
    used_aliases: set[str] = set()
    for item in selected:
        alias = str(item['output_name'] or item['name'])
        if alias in used_aliases:
            alias = f'{item["table"]}__{alias}'
        used_aliases.add(alias)
        aliases.append(alias)
        select_sql.append(
            f'{_quote(item["table"])}.{_quote(item["name"])} AS {_quote(alias)}'
        )
    clauses, bound = _where(catalogue, values, included)
    sql = (
        'SELECT '
        + ', '.join(select_sql)
        + f' FROM {_quote(root)}'
        + ''.join(join_sql)
    )
    if clauses:
        sql += ' WHERE ' + ' AND '.join(clauses)
    limit = values.get('limit', _MAX_ROWS)
    if limit is None:
        limit = _MAX_ROWS
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise DbReadError('limit doit être un entier')
    if limit < 1:
        raise DbReadError('limit doit être positif')
    bound.append(min(limit, _MAX_ROWS))
    sql += ' LIMIT ?'
    return sql, bound, aliases


def execute_db_read(
    conn: sqlite3.Connection,
    tool_id: str,
    arguments: Mapping[str, Any],
    *,
    fixed_joins: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Exécute un tool DB individualisé et retourne des lignes bornées."""
    sql, bound, aliases = build_db_read_query(
        conn, tool_id, arguments, fixed_joins=fixed_joins
    )
    rows = conn.execute(sql, bound).fetchall()
    data = [
        {alias: row[index] for index, alias in enumerate(aliases)}
        for row in rows
    ]
    return {'ok': True, 'tool_id': tool_id, 'data': data}


def openai_schema_for_tool(
    conn: sqlite3.Connection, tool_id: str
) -> dict[str, Any]:
    """Construit le function schema depuis le catalogue relationnel."""
    from serge.db.query_schema import build_openai_schema

    catalogue = tool_catalogue(conn, tool_id)
    _validate_catalogue(conn, catalogue)
    return build_openai_schema(catalogue, tool_id)
