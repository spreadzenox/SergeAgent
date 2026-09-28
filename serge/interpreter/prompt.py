#!/usr/bin/env python3
"""Préparer ce qu'une invocation LLM reçoit, et appeler le modèle.

Le prompt est assemblé à partir de la base : le bloc « Qui est Serge » si
l'invocation le demande (la chaîne, sa place, ce qui vient avant et après
elle), ses consignes et le format de réponse attendu. Le message suivant
contient ce qu'elle reçoit d'office : ses lectures (ce qu'elle doit
traiter), la version courte des tables à comparer, et ses leçons. Le
modèle peut ensuite appeler ses outils, dans la limite réglée sur
l'invocation.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from serge.interpreter.intro import lessons_block, serge_intro
from serge.interpreter.output import Field, describe_format
from serge.interpreter.seen import short_blocks
from serge.interpreter.settings import (
    fill_prompt,
    load_settings,
    prompt_values,
    resolve_count,
)
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
    step_id: str


def load_invocation(
    conn: sqlite3.Connection, invocation_id: str
) -> Invocation:
    row = conn.execute(
        'SELECT id, title, type, model_tier, prompt, gets_serge_intro,'
        ' default_max_rows, max_tool_turns, capability_id, step_id'
        ' FROM invocations'
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
        str(row[9] or ''),
    )


def given_blocks(
    conn: sqlite3.Connection,
    inv: Invocation,
    task_id: str,
    task: Mapping[str, str],
) -> list[str]:
    """Ce qu'elle reçoit d'office, en blocs du prompt.

    D'abord chaque lecture donnée d'office (ce qu'elle doit traiter,
    réglé sur ses liens aux outils), puis la version courte des tables à
    comparer, puis ses leçons. Exemple : « Le cycle en cours », suivi de
    ses lignes. Le nombre de lignes données et laissées de côté est noté
    en base (``task_inputs``, ``task_seen_tables``), pour Mission Control.

    Une lecture réglée « par paquets » (``batch_size``) est découpée : il
    y a alors un message par paquet, chacun avec les autres blocs, et le
    modèle est appelé une fois par paquet. Exemple : trier 60 pages par
    paquets de 20 donne trois appels.

    Returns:
        Le contenu du message, un par paquet (un seul sans paquets).
    """
    settings = load_settings(conn, inv.id)
    blocks: list[str] = []
    batched: tuple[int, str, list] | None = None
    for link_id, tool_id, label, max_rows, batch in conn.execute(
        'SELECT id, tool_id, label, max_rows, batch_size FROM invocation_tools'
        " WHERE invocation_id=? AND mode='given' ORDER BY position",
        (inv.id,),
    ).fetchall():
        result = run_tool(conn, inv.id, int(link_id), str(tool_id), {}, task)
        rows = result.get('rows')
        limit = int(max_rows) or inv.default_max_rows
        size = resolve_count(str(batch), settings)
        if isinstance(rows, list):
            total = int(result.get('total') or len(rows))
            shown, left = rows[:limit], max(0, total - min(len(rows), limit))
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
        title = f'## {label or tool_id}'
        if size and batched is None and isinstance(rows, list):
            batched = (
                len(blocks),
                title,
                [shown[i : i + size] for i in range(0, len(shown), size)],
            )
            blocks.append('')
            continue
        blocks.append(f'{title}\n{body}')
    blocks += short_blocks(conn, inv.id, task_id, inv.default_max_rows)
    lessons = lessons_block(
        conn, inv.id, inv.step_id, task_id, inv.default_max_rows
    )
    if lessons:
        blocks.append(lessons)
    if batched is None:
        return ['\n\n'.join(blocks)]
    place, title, chunks = batched
    contents = []
    for number, chunk in enumerate(chunks or [[]], 1):
        body = json.dumps(chunk, ensure_ascii=False, default=str)
        head = f'{title} (paquet {number} sur {max(1, len(chunks))})'
        parts = [*blocks[:place], f'{head}\n{body}', *blocks[place + 1 :]]
        contents.append('\n\n'.join(p for p in parts if p))
    return contents


def system_prompt(
    conn: sqlite3.Connection, inv: Invocation, fields: list[Field]
) -> str:
    parts: list[str] = []
    if inv.gets_serge_intro:
        parts.append(serge_intro(conn, inv.id, inv.title, inv.step_id))
    parts.append(fill_prompt(inv.prompt.strip(), prompt_values(conn, inv.id)))
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
    pas de paramètre figé. Un outil qui ne lui sert à rien n'est pas
    proposé : « Lire les tables que je vois », pour une invocation qui ne
    voit aucune table.
    """
    schemas: list[dict[str, Any]] = []
    links: dict[str, int | None] = {}
    for link_id, tool_id in conn.execute(
        'SELECT id, tool_id FROM invocation_tools'
        " WHERE invocation_id=? AND mode='callable' ORDER BY position",
        (inv.id,),
    ).fetchall():
        fixed = set(fixed_params(conn, inv.id, int(link_id), task))
        schema = tool_schema(conn, str(tool_id), fixed, inv.id)
        if schema is not None:
            schemas.append(schema)
            links[str(tool_id)] = int(link_id)
    for (tool_id,) in conn.execute(
        'SELECT t.id FROM tools t JOIN capabilities c ON c.id=t.capability_id'
        ' WHERE t.montre_partout=1 AND c.available=1 ORDER BY t.id'
    ).fetchall():
        schema = tool_schema(conn, str(tool_id), set(), inv.id)
        if str(tool_id) not in links and schema is not None:
            schemas.append(schema)
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
    outil. Un outil réglé avec ``max_calls`` (un nombre ou un réglage)
    répond « limite atteinte » au-delà : exemple, au plus 10 recherches.
    """
    schemas, links = callable_tools(conn, inv, task)
    limits = _call_limits(conn, inv, links)
    calls: dict[str, int] = {}
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
                        _limited_call(
                            conn, inv, links, limits, calls, call, task
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


def _call_limits(
    conn: sqlite3.Connection, inv: Invocation, links: Mapping[str, int | None]
) -> dict[str, int]:
    """Le nombre maximum d'appels de chaque outil qui en a un."""
    settings = load_settings(conn, inv.id)
    limits: dict[str, int] = {}
    for name, link_id in links.items():
        if link_id is None:
            continue
        row = conn.execute(
            'SELECT max_calls FROM invocation_tools WHERE id=?', (link_id,)
        ).fetchone()
        limit = resolve_count(str(row[0]), settings) if row else None
        if limit is not None:
            limits[name] = limit
    return limits


def _limited_call(
    conn: sqlite3.Connection,
    inv: Invocation,
    links: Mapping[str, int | None],
    limits: Mapping[str, int],
    calls: dict[str, int],
    call: Any,
    task: Mapping[str, str],
) -> dict[str, Any]:
    done = calls.get(call.name, 0)
    if call.name in limits and done >= limits[call.name]:
        return {
            'ok': False,
            'code': 'limite_atteinte',
            'detail': f'au plus {limits[call.name]} appels de cet outil',
        }
    calls[call.name] = done + 1
    return _call_tool(conn, inv, links, call.name, call.arguments, task)


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
