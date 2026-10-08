#!/usr/bin/env python3
"""Exécuter un outil : une capacité du code, avec les réglages de l'outil.

Le code n'a qu'une fonction par capacité. Un outil (table ``tools``) dit
quelle capacité il utilise ; le lien entre une invocation et un outil
(``invocation_tools``) dit s'il est lu d'office (Serge le lit avant
l'appel et met le résultat dans le prompt) ou appelable, et quels
paramètres sont figés. Le modèle ne peut jamais changer un paramètre figé.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from typing import Any

from serge.conversations.contact import add_contact_address, contact_search
from serge.conversations.followups import due_followups
from serge.conversations.receive import receive_messages
from serge.conversations.send import send_message
from serge.conversations.thread import contact_thread
from serge.conversations.unsubscribe import unsubscribe_contact
from serge.interpreter.seen import CHOICES, read_seen_table, row_history
from serge.interpreter.settings import load_settings
from serge.policy_store import policy_en_vigueur
from serge.tickets.inform import inform_owners

Runner = Callable[
    [sqlite3.Connection, str, dict[str, Any], str], dict[str, Any]
]


def _db_read(
    conn: sqlite3.Connection, tool_id: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    from serge.db.query_builder import execute_db_read

    result = execute_db_read(conn, tool_id, args)
    return {'ok': True, 'rows': result['data'], 'total': result['total']}


def _web_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    from serge.listen.web import search_public

    pol = policy_en_vigueur(conn)
    limit = int(args.get('limit') or pol['tools']['search_results'])
    result = dict(
        search_public(str(args.get('query') or ''), limit, pol['web'])
    )
    # Les résultats sous un seul nom : ce que rend un outil repart au
    # modèle à chaque tour, un doublon coûterait deux fois.
    rows = result.pop('results', [])
    return {**result, 'rows': rows}


def _memory_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    from serge.memory.search import memory_search

    types = args.get('types')
    result = dict(
        memory_search(
            conn,
            str(args.get('query') or ''),
            point=inv,
            types=list(types) if isinstance(types, list) else None,
            top_k=int(
                args.get('top_k')
                or policy_en_vigueur(conn)['tools']['memory_results']
            ),
        )
    )
    rows = result.pop('results', [])
    return {**result, 'rows': rows}


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


def _page_read(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Lire une page : par son adresse, ou par sa ligne dans une table.

    Avec ``table`` et ``id``, seule une page déjà en base peut être lue
    (son adresse est dans la colonne ``url``).
    """
    from serge.interpreter.rules import safe_name
    from serge.listen.page import read_page

    url = str(args.get('url') or '')
    table = str(args.get('table') or '')
    if table:
        row = conn.execute(
            f'SELECT url FROM "{safe_name(table)}" WHERE id=?',
            (str(args.get('id') or ''),),
        ).fetchone()
        if row is None:
            return {'ok': False, 'code': 'page_inconnue', 'rows': []}
        url = str(row[0])
    result = dict(
        read_page(
            url,
            int(args.get('max_lines') or 0),
            policy_en_vigueur(conn)['web'],
        )
    )
    rows = result.pop('lines', [])
    return {**result, 'rows': rows}


def _rss_read(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Lire un flux RSS : ses pages, avec un aperçu de quelques lignes.

    Sans nombre donné par le modèle, les valeurs par défaut de la page
    Pipeline (« Outils, valeurs par défaut »).
    """
    from serge.listen.collectors import fetch_rss
    from serge.listen.page import text_lines

    pol = policy_en_vigueur(conn)
    lines = int(args.get('max_lines') or pol['tools']['feed_preview_lines'])
    rows = []
    for item in fetch_rss(
        str(args.get('url') or ''),
        'rss',
        timeout=float(pol['web']['feed_timeout_s']),
        max_items=int(args.get('max_items') or pol['tools']['feed_items']),
    ):
        apercu = text_lines(
            item['excerpt'], int(pol['web']['line_max_chars'])
        )[1][:lines]
        rows.append(
            {
                'url': item['url'],
                'title': item['title'],
                'excerpt': '\n'.join(apercu),
                'published': item['published'],
            }
        )
    return {'ok': True, 'rows': rows}


def _echo(
    _conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    return dict(args)


RUNNERS: dict[str, Runner] = {
    'echo': _echo,
    'receive_messages': receive_messages,
    'contact_thread': contact_thread,
    'send_message': send_message,
    'due_followups': due_followups,
    'unsubscribe_contact': unsubscribe_contact,
    'contact_search': contact_search,
    'add_contact_address': add_contact_address,
    'inform_owners': inform_owners,
    'db_read': _db_read,
    'web_search': _web_search,
    'memory_search': _memory_search,
    'request_capability': _request_capability,
    'page_read': _page_read,
    'rss_read': _rss_read,
    'seen_table_read': read_seen_table,
    'row_history': row_history,
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
    invocation_tool_id: int | None,
    task: Mapping[str, str],
) -> dict[str, str]:
    """Les paramètres figés d'un outil (ou de la capacité, si l'id vaut 0).

    Un outil donné partout n'a pas de lien (``None``), donc rien de figé.
    """
    out: dict[str, str] = {}
    if invocation_tool_id is None:
        return out
    settings = load_settings(conn, invocation_id)
    for name, source, value in conn.execute(
        'SELECT param_name, source, value FROM invocation_tool_params'
        ' WHERE invocation_id=? AND invocation_tool_id=?',
        (invocation_id, invocation_tool_id),
    ).fetchall():
        if source == 'task':
            out[str(name)] = task.get(str(value), '')
        elif source == 'setting':
            out[str(name)] = settings.get(str(value), '')
        else:
            out[str(name)] = str(value)
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
    invocation_tool_id: int | None,
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
    conn: sqlite3.Connection,
    tool_id: str,
    fixed: set[str],
    invocation_id: str = '',
) -> dict[str, Any] | None:
    """Le schéma d'un outil appelable, tel qu'on le montre au modèle.

    Les paramètres figés n'y figurent pas : le modèle n'a pas à les
    choisir. Pour certaines capacités, le schéma dépend de l'invocation :
    « Lire les tables que je vois » ne propose que ses tables. ``None`` :
    l'outil ne sert à rien à cette invocation.
    """
    capability = tool_capability(conn, tool_id)
    choices = CHOICES.get(capability)
    chosen = choices(conn, invocation_id) if choices else ({}, '')
    if chosen is None:
        return None
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
        enums, extra = chosen
        for name, values in enums.items():
            if name in properties:
                properties[name]['enum'] = values
        description = f'{doc[0]}. {doc[1]}' if doc else tool_id
        schema: dict[str, Any] = {
            'type': 'function',
            'function': {
                'name': tool_id,
                'description': f'{description} {extra}'.strip(),
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
