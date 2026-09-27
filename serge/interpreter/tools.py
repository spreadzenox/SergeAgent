#!/usr/bin/env python3
"""Exécuter un outil : une capacité du code, avec les réglages de l'outil.

Le code n'a qu'une fonction par capacité. Un outil (table ``tools``) dit
quelle capacité il utilise ; le lien entre une invocation et un outil
(``invocation_tools``) dit s'il est donné d'office ou appelable, et quels
paramètres sont figés. Le modèle ne peut jamais changer un paramètre figé.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

Runner = Callable[
    [sqlite3.Connection, str, dict[str, Any], str], dict[str, Any]
]


def _db_read(
    conn: sqlite3.Connection, tool_id: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    from serge.db.query_builder import execute_db_read

    result = execute_db_read(conn, tool_id, args)
    return {'ok': True, 'rows': result['data']}


def _web_search(
    _conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    from serge.listen.web import search_public

    result = search_public(
        str(args.get('query') or ''), int(args.get('limit') or 5)
    )
    return {**result, 'rows': result.get('results', [])}


def _memory_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    from serge.memory.search import memory_search

    types = args.get('types')
    result = memory_search(
        conn,
        str(args.get('query') or ''),
        point=inv,
        types=list(types) if isinstance(types, list) else None,
        top_k=int(args.get('top_k') or 5),
    )
    return {**result, 'rows': result.get('results', [])}


def _request_capability(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    from serge.demande_capacite import poser_demande

    return poser_demande(
        conn,
        str(args.get('need') or ''),
        point=inv,
        contexte=str(args.get('context') or ''),
    )


def _echo(
    _conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    return dict(args)


RUNNERS: dict[str, Runner] = {
    'echo': _echo,
    'db_read': _db_read,
    'web_search': _web_search,
    'memory_search': _memory_search,
    'request_capability': _request_capability,
}


class ToolError(ValueError):
    """Un outil ne peut pas être exécuté."""


def tool_capability(conn: sqlite3.Connection, tool_id: str) -> str:
    """La capacité qu'utilise un outil."""
    row = conn.execute(
        'SELECT capability_id FROM tools WHERE id=?', (tool_id,)
    ).fetchone()
    if row is None or not str(row[0] or ''):
        raise ToolError(f'outil sans capacité : {tool_id}')
    return str(row[0])


def fixed_params(
    conn: sqlite3.Connection,
    invocation_id: str,
    invocation_tool_id: int,
    task: Mapping[str, str],
) -> dict[str, str]:
    """Les paramètres figés d'un outil (ou de la capacité, si l'id vaut 0)."""
    out: dict[str, str] = {}
    for name, source, value in conn.execute(
        'SELECT param_name, source, value FROM invocation_tool_params'
        ' WHERE invocation_id=? AND invocation_tool_id=?',
        (invocation_id, invocation_tool_id),
    ).fetchall():
        out[str(name)] = (
            task.get(str(value), '') if source == 'task' else str(value)
        )
    return out


def run_capability(
    conn: sqlite3.Connection,
    capability_id: str,
    tool_id: str,
    args: Mapping[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """Appelle la fonction du code qui porte cette capacité."""
    runner = RUNNERS.get(capability_id)
    if runner is None:
        raise ToolError(f'capacité absente du code : {capability_id}')
    return runner(conn, tool_id, dict(args), invocation_id)


def run_tool(
    conn: sqlite3.Connection,
    invocation_id: str,
    invocation_tool_id: int,
    tool_id: str,
    model_args: Mapping[str, Any],
    task: Mapping[str, str],
) -> dict[str, Any]:
    """Exécute un outil : les paramètres figés passent devant ceux du modèle."""
    args = {
        **dict(model_args),
        **fixed_params(conn, invocation_id, invocation_tool_id, task),
    }
    return run_capability(
        conn, tool_capability(conn, tool_id), tool_id, args, invocation_id
    )


def tool_schema(
    conn: sqlite3.Connection, tool_id: str, fixed: set[str]
) -> dict[str, Any]:
    """Le schéma d'un outil appelable, tel qu'on le montre au modèle.

    Les paramètres figés n'y figurent pas : le modèle n'a pas à les
    choisir.
    """
    capability = tool_capability(conn, tool_id)
    if capability == 'db_read':
        from serge.db.query_builder import openai_schema_for_tool

        schema = openai_schema_for_tool(conn, tool_id)
    else:
        doc = conn.execute(
            'SELECT titre, doc_md FROM tools WHERE id=?', (tool_id,)
        ).fetchone()
        properties: dict[str, Any] = {}
        required: list[str] = []
        types = {
            'text': 'string',
            'number': 'number',
            'bool': 'boolean',
            'list': 'array',
        }
        for name, kind, needed, description in conn.execute(
            'SELECT name, type, required, description FROM capability_params'
            ' WHERE capability_id=? ORDER BY position',
            (capability,),
        ).fetchall():
            prop: dict[str, Any] = {
                'type': types.get(str(kind), 'string'),
                'description': str(description),
            }
            if kind == 'list':
                prop['items'] = {'type': 'string'}
            properties[str(name)] = prop
            if needed:
                required.append(str(name))
        schema: dict[str, Any] = {
            'type': 'function',
            'function': {
                'name': tool_id,
                'description': f'{doc[0]}. {doc[1]}' if doc else tool_id,
                'parameters': {
                    'type': 'object',
                    'properties': properties,
                    'required': required,
                },
            },
        }
    return _without_fixed(schema, fixed)


def _without_fixed(schema: dict[str, Any], fixed: set[str]) -> dict[str, Any]:
    """Retire du schéma les paramètres figés."""
    function: Any = schema.get('function')
    params: Any = (
        function.get('parameters') if isinstance(function, dict) else None
    )
    if not isinstance(params, dict):
        return schema
    props: Any = params.get('properties')
    if isinstance(props, dict):
        for name in fixed:
            props.pop(name, None)
    needed: Any = params.get('required')
    if isinstance(needed, list):
        params['required'] = [n for n in needed if n not in fixed]
    return schema
