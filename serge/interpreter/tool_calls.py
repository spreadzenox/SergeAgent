#!/usr/bin/env python3
"""Appeler les outils qu'un modèle demande, pendant un tour d'outils.

Chaque appel respecte la limite réglée sur l'outil (« au plus 10
recherches »), est noté au journal (l'outil, ses paramètres en court, et
s'il a marché), et rend un résultat borné : il repart au modèle à chaque
tour suivant. Les vieilles captures d'écran sortent de l'historique.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event
from serge.interpreter.settings import load_settings, resolve_count
from serge.interpreter.tools import run_tool

# Ce que le journal garde des paramètres d'un appel d'outil.
JOURNAL_MAX = 300


def drop_old_images(
    history: list[dict[str, Any]], kept: int, note: str
) -> None:
    """Ne garde dans l'historique que les ``kept`` dernières images.

    Tout l'historique repart au modèle à chaque tour : sans cela, chaque
    capture serait payée à chaque tour suivant. Une image retirée devient
    un texte court (``note``). Exemple : avec 3, la quatrième capture fait
    retirer la première.
    """
    seen = 0
    for message in reversed(history):
        content = message.get('content')
        if not isinstance(content, list):
            continue
        for index in range(len(content) - 1, -1, -1):
            part = content[index]
            if not isinstance(part, dict) or part.get('type') != 'image_url':
                continue
            seen += 1
            if seen > kept:
                # Un texte vidé sur la page Pipeline n'est pas envoyé.
                content[index] = {'type': 'text', 'text': note or '…'}


def bounded(texte: str, limite: int, note: str) -> str:
    """Un résultat d'outil coupé à ``limite`` caractères, avec une note
    dont le repère ``{reste}`` dit combien de caractères ont été coupés."""
    if limite <= 0 or len(texte) <= limite:
        return texte
    reste = str(len(texte) - limite)
    return f'{texte[:limite]}… {note.replace("{reste}", reste)}'.rstrip()


def call_limits(
    conn: sqlite3.Connection,
    invocation_id: str,
    links: Mapping[str, int | None],
) -> dict[str, int]:
    """Le nombre maximum d'appels de chaque outil qui en a un."""
    settings = load_settings(conn, invocation_id)
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


def limited_call(
    conn: sqlite3.Connection,
    invocation_id: str,
    links: Mapping[str, int | None],
    limits: Mapping[str, int],
    calls: dict[str, int],
    call: Any,
    task: Mapping[str, str],
) -> dict[str, Any]:
    """Un appel d'outil demandé par le modèle, noté au journal.

    Exemple d'événement ``tool.call`` : l'outil ``navigateur_agir``, ses
    paramètres ``{"action": "cliquer", "ref": "e7"}``, et ``ok`` vrai.
    """
    done = calls.get(call.name, 0)
    if call.name in limits and done >= limits[call.name]:
        outcome: dict[str, Any] = {
            'ok': False,
            'code': 'limite_atteinte',
            'detail': f'au plus {limits[call.name]} appels de cet outil',
        }
    else:
        calls[call.name] = done + 1
        outcome = _call_tool(
            conn, invocation_id, links, call.name, call.arguments, task
        )
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='tool.call',
        payload={
            'task': task.get('task_id', ''),
            'tool': call.name,
            'args': str(call.arguments or '')[:JOURNAL_MAX],
            'ok': outcome.get('ok', True) is not False,
            'code': str(outcome.get('code') or ''),
        },
    )
    return outcome


def _call_tool(
    conn: sqlite3.Connection,
    invocation_id: str,
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
        return run_tool(conn, invocation_id, links[name], name, args, task)
    except Exception as exc:  # noqa: BLE001 — un outil en échec ne tue pas l'invocation
        return {'ok': False, 'code': 'echec', 'detail': str(exc)[:200]}
