#!/usr/bin/env python3
"""Préparer ce qu'une invocation LLM reçoit, et appeler le modèle.

Le prompt est assemblé à partir de la base : le texte « Qui est Serge » si
l'invocation le demande, ses consignes, le format de réponse attendu, puis
chaque outil donné d'office, lu avant l'appel. Le modèle peut ensuite
appeler ses outils appelables, dans la limite réglée sur l'invocation.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from serge.interpreter.output import Field, describe_format
from serge.interpreter.settings import fill_prompt, load_settings
from serge.interpreter.tools import fixed_params, run_tool, tool_schema
from serge.llm.client import ChatResult


@dataclass(frozen=True)
class Invocation:
    id: str
    title: str
    type: str
    model_tier: str
    prompt: str
    gets_serge_intro: bool
    default_max_rows: int
    max_tool_turns: int
    capability_id: str


def load_invocation(
    conn: sqlite3.Connection, invocation_id: str
) -> Invocation:
    row = conn.execute(
        'SELECT id, title, type, model_tier, prompt, gets_serge_intro,'
        ' default_max_rows, max_tool_turns, capability_id FROM invocations'
        ' WHERE id=?',
        (invocation_id,),
    ).fetchone()
    if row is None:
        raise KeyError(invocation_id)
    return Invocation(
        str(row[0]),
        str(row[1]),
        str(row[2]),
        str(row[3]),
        str(row[4]),
        bool(row[5]),
        int(row[6]),
        int(row[7]),
        str(row[8]),
    )


def given_blocks(
    conn: sqlite3.Connection,
    inv: Invocation,
    task_id: str,
    task: Mapping[str, str],
) -> str:
    """Lit chaque outil donné d'office et en fait un bloc du prompt.

    Exemple : « Les business déjà connus (50 montrés, 90 laissés de
    côté) », suivi des lignes. Le nombre de lignes données et laissées est
    noté dans ``task_inputs``, pour Mission Control.
    """
    blocks: list[str] = []
    for link_id, tool_id, label, max_rows in conn.execute(
        'SELECT id, tool_id, label, max_rows FROM invocation_tools'
        " WHERE invocation_id=? AND mode='given' ORDER BY position",
        (inv.id,),
    ).fetchall():
        result = run_tool(conn, inv.id, int(link_id), str(tool_id), {}, task)
        rows = result.get('rows')
        limit = int(max_rows) or inv.default_max_rows
        if isinstance(rows, list):
            shown, left = rows[:limit], max(0, len(rows) - limit)
            body = json.dumps(shown, ensure_ascii=False, default=str)
            if left:
                body += f'\n({left} autres lignes ne sont pas montrées.)'
        else:
            shown, left = [result], 0
            body = json.dumps(result, ensure_ascii=False, default=str)
        conn.execute(
            'INSERT OR REPLACE INTO task_inputs(task_id, invocation_tool_id,'
            ' rows_given, rows_left_out) VALUES(?,?,?,?)',
            (task_id, int(link_id), len(shown), left),
        )
        blocks.append(f'## {label or tool_id}\n{body}')
    return '\n\n'.join(blocks)


def system_prompt(
    conn: sqlite3.Connection, inv: Invocation, fields: list[Field]
) -> str:
    parts: list[str] = []
    if inv.gets_serge_intro:
        row = conn.execute(
            "SELECT body FROM serge_texts WHERE id='presentation'"
        ).fetchone()
        if row and str(row[0]).strip():
            parts.append(f'# Qui est Serge\n{str(row[0]).strip()}')
        parts.append(f'# Ta place\nTu es « {inv.title} ».')
    parts.append(fill_prompt(inv.prompt.strip(), load_settings(conn, inv.id)))
    fmt = describe_format(fields)
    if fmt:
        parts.append(f'# Format de ta réponse\n{fmt}')
    return '\n\n'.join(p for p in parts if p)


def callable_tools(
    conn: sqlite3.Connection, inv: Invocation, task: Mapping[str, str]
) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    """Les schémas des outils appelables, et leur lien (par nom d'outil).

    En plus des outils de l'invocation, chaque invocation LLM peut appeler
    les outils marqués « partout » (``tools.montre_partout``), par exemple
    « Demander une nouvelle capacité ». Ceux-là n'ont pas de lien, donc
    pas de paramètre figé.
    """
    schemas: list[dict[str, Any]] = []
    links: dict[str, int | None] = {}
    for link_id, tool_id in conn.execute(
        'SELECT id, tool_id FROM invocation_tools'
        " WHERE invocation_id=? AND mode='callable' ORDER BY position",
        (inv.id,),
    ).fetchall():
        fixed = set(fixed_params(conn, inv.id, int(link_id), task))
        schemas.append(tool_schema(conn, str(tool_id), fixed))
        links[str(tool_id)] = int(link_id)
    for (tool_id,) in conn.execute(
        'SELECT t.id FROM tools t JOIN capabilities c ON c.id=t.capability_id'
        ' WHERE t.montre_partout=1 AND c.available=1 ORDER BY t.id'
    ).fetchall():
        if str(tool_id) not in links:
            schemas.append(tool_schema(conn, str(tool_id), set()))
            links[str(tool_id)] = None
    return schemas, links


Caller = Callable[..., ChatResult]


def converse(
    conn: sqlite3.Connection,
    inv: Invocation,
    messages: list[dict[str, Any]],
    task: Mapping[str, str],
    *,
    caller: Caller,
    api_key: str,
    model: str,
) -> tuple[ChatResult, list[dict[str, Any]]]:
    """Laisse le modèle appeler ses outils, puis rend sa réponse finale.

    Après ``max_tool_turns`` tours d'outils, le modèle doit répondre sans
    outil.
    """
    schemas, links = callable_tools(conn, inv, task)
    history = [dict(m) for m in messages]
    tokens_in = tokens_out = latency = 0
    turns = 0
    while True:
        force_text = not schemas or turns >= inv.max_tool_turns
        result = caller(
            api_key,
            model,
            history,
            tools=schemas or None,
            tool_choice='none' if force_text and schemas else None,
        )
        tokens_in += result.tokens_in
        tokens_out += result.tokens_out
        latency += result.latency_ms
        if force_text or not result.tool_calls:
            final = ChatResult(
                result.text,
                tokens_in,
                tokens_out,
                result.model or model,
                latency,
            )
            return final, history
        history.append(
            {
                'role': 'assistant',
                'content': result.text or None,
                'tool_calls': [
                    {
                        'id': call.id,
                        'type': 'function',
                        'function': {
                            'name': call.name,
                            'arguments': call.arguments,
                        },
                    }
                    for call in result.tool_calls
                ],
            }
        )
        for call in result.tool_calls:
            history.append(
                {
                    'role': 'tool',
                    'tool_call_id': call.id,
                    'content': json.dumps(
                        _call_tool(
                            conn, inv, links, call.name, call.arguments, task
                        ),
                        ensure_ascii=False,
                        default=str,
                    ),
                }
            )
        turns += 1
        # Les outils ont pu écrire (un ticket, une demande) : on enregistre
        # avant de rappeler le modèle, pour ne pas bloquer la base pendant
        # l'appel.
        conn.commit()


def _call_tool(
    conn: sqlite3.Connection,
    inv: Invocation,
    links: Mapping[str, int | None],
    name: str,
    raw_args: str,
    task: Mapping[str, str],
) -> dict[str, Any]:
    if name not in links:
        return {'ok': False, 'code': 'outil_non_autorise'}
    try:
        args = json.loads(raw_args or '{}')
    except json.JSONDecodeError:
        return {'ok': False, 'code': 'arguments_illisibles'}
    if not isinstance(args, dict):
        return {'ok': False, 'code': 'arguments_illisibles'}
    try:
        return run_tool(conn, inv.id, links[name], name, args, task)
    except Exception as exc:  # noqa: BLE001 — un outil en échec ne tue pas l'invocation
        return {'ok': False, 'code': 'echec', 'detail': str(exc)[:200]}
