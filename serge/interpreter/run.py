#!/usr/bin/env python3
"""Exécuter une tâche : toujours les mêmes étapes, pour toute invocation.

1. Préparer : lire les réglages de l'invocation et ce qui est donné
   d'office.
2. Produire une réponse : le modèle (invocation LLM) ou la capacité
   (invocation sans LLM).
3. Vérifier le format ; redemander au modèle, avec l'erreur, deux fois au
   plus.
4. Écrire la réponse selon les règles en base.
5. Passer la main : liens et déclencheurs.

Rien ici ne connaît une invocation en particulier.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.db.store import append_event, utcnow
from serge.interpreter.flow import fire_row_triggers, pass_links
from serge.interpreter.output import check_answer, load_fields, parse_answer
from serge.interpreter.prompt import (
    Caller,
    Invocation,
    converse,
    given_blocks,
    load_invocation,
    system_prompt,
)
from serge.interpreter.tasks import finish_task, start_task, task_params
from serge.interpreter.tools import fixed_params, run_capability
from serge.interpreter.writer import write_answer
from serge.llm.client import ChatResult
from serge.llm.runtime import budget_reached
from serge.policy_snapshots import policy_en_vigueur

TIER_TO_OLD = {'fast': 'T1', 'mid': 'T2', 'smart': 'T3'}


class AnswerError(ValueError):
    """La réponse ne respecte pas le format, même après les relances."""


def resolve_model(
    conn: sqlite3.Connection, tier: str, root: Path | None = None
) -> tuple[str, str]:
    """Le modèle derrière un niveau : réglé en base, sinon celui de l'instance."""
    row = conn.execute(
        'SELECT model FROM llm_models WHERE tier=?', (tier,)
    ).fetchone()
    if row and str(row[0] or ''):
        return str(row[0]), ''
    from serge.llm.runtime import resolve_model as instance_model

    return instance_model(TIER_TO_OLD.get(tier, 'T2'), root)


def _record_usage(
    conn: sqlite3.Connection,
    inv: Invocation,
    model: str,
    result: ChatResult | None,
    verdict: str,
) -> None:
    """Note un appel au modèle, et l'enregistre aussitôt.

    ``result`` vaut ``None`` pour un appel raté : il n'a ni jetons ni coût.
    Le coût est celui qu'OpenRouter a facturé, quand il le donne.
    """
    conn.execute(
        'INSERT INTO llm_usage(point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, cost_usd, created_at)'
        ' VALUES(?,?,?,?,?,?,?,?,?)',
        (
            inv.id,
            inv.model_tier,
            (result.model or model) if result else model,
            result.tokens_in if result else 0,
            result.tokens_out if result else 0,
            result.latency_ms if result else 0,
            verdict,
            result.cost_usd if result else None,
            utcnow(),
        ),
    )
    conn.commit()


def _llm_answer(
    conn: sqlite3.Connection,
    inv: Invocation,
    task_id: str,
    task: Mapping[str, str],
    *,
    caller: Caller | None,
    root: Path | None,
) -> Any:
    """La réponse du modèle, un appel par paquet s'il y en a.

    Les réponses des paquets sont réunies : les listes sont mises bout à
    bout (exemple : les pages triées de chaque paquet).
    """
    fields = load_fields(conn, inv.id)
    contents = given_blocks(conn, inv, task_id, task)
    conn.commit()
    model, _referer = resolve_model(conn, inv.model_tier, root)
    api_key = ''
    if caller is None:
        from serge.llm.client import chat
        from serge.llm.runtime import read_api_key

        caller, api_key = chat, read_api_key(root)
    system = system_prompt(conn, inv, fields)
    answers = []
    for user in contents:
        if task:
            params = json.dumps(dict(task), ensure_ascii=False)
            user = f'## Paramètres de la tâche\n{params}\n\n{user}'.strip()
        messages: list[dict[str, Any]] = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user or 'Commence.'},
        ]
        answers.append(
            _ask(conn, inv, messages, task, fields, caller, api_key, model)
        )
    return _merge(answers)


def _merge(answers: list[Any]) -> Any:
    """Réunit les réponses des paquets : les listes bout à bout."""
    if len(answers) == 1:
        return answers[0]
    merged: dict[str, Any] = {}
    for answer in answers:
        for key, value in (answer or {}).items():
            if isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = [*merged[key], *value]
            else:
                merged[key] = value
    return merged


def _ask(
    conn: sqlite3.Connection,
    inv: Invocation,
    messages: list[dict[str, Any]],
    task: Mapping[str, str],
    fields: list,
    caller: Caller,
    api_key: str,
    model: str,
) -> Any:
    """Un appel au modèle, avec ses outils ; redemandé si le format est faux.

    Chaque appel est noté aussitôt (tours d'outils, échecs compris) et
    enregistré : si la tâche échoue ensuite, ce qu'elle a coûté reste
    visible, et compte dans les plafonds du jour et du mois. Quand un
    plafond est atteint en plein travail, le modèle doit répondre sans plus
    d'outil ; la tâche finit, et les suivantes attendent le lendemain (ou
    le mois suivant).
    """

    def record(result: ChatResult | None, verdict: str) -> None:
        _record_usage(conn, inv, model, result, verdict)

    policy = policy_en_vigueur(conn)
    quotas = policy.get('quotas') or {}
    # Les nouveaux essais d'une réponse mal formée (policy, page Policy).
    retries = int(quotas.get('llm_recalls_json', 0) or 0)
    last_errors: list[str] = []
    for attempt in range(retries + 1):
        result, history = converse(
            conn,
            inv,
            messages,
            task,
            caller=caller,
            api_key=api_key,
            model=model,
            record=record,
            stop=lambda: bool(budget_reached(conn, policy_en_vigueur(conn))),
            # Une redemande de format corrige la réponse, sans outil.
            tools_allowed=attempt == 0,
            max_result_chars=int(
                quotas.get('llm_outil_resultat_max_caracteres', 0) or 0
            ),
        )
        if not fields:
            record(result, 'ok')
            return {'text': result.text}
        try:
            answer = parse_answer(result.text)
            last_errors = check_answer(fields, answer)
        except (json.JSONDecodeError, ValueError):
            answer, last_errors = (
                None,
                ['la réponse n’est pas un objet JSON lisible'],
            )
        record(result, 'ok' if not last_errors else 'format_invalide')
        if not last_errors:
            return answer
        if attempt < retries:
            messages = [
                *history,
                {'role': 'assistant', 'content': result.text},
                {
                    'role': 'user',
                    'content': 'Ta réponse ne respecte pas le format : '
                    + '; '.join(last_errors)
                    + '. Rends la réponse corrigée, en JSON seulement.',
                },
            ]
    raise AnswerError('; '.join(last_errors))


def _capability_answer(
    conn: sqlite3.Connection, inv: Invocation, task: Mapping[str, str]
) -> Any:
    args: dict[str, Any] = dict(fixed_params(conn, inv.id, 0, task))
    tool_id = str(args.pop('tool_id', ''))
    answer = run_capability(conn, inv.capability_id, tool_id, args, inv.id)
    fields = load_fields(conn, inv.id)
    errors = check_answer(fields, answer) if fields else []
    if errors:
        raise AnswerError('; '.join(errors))
    return answer


def run_task(
    conn: sqlite3.Connection,
    task_id: str,
    *,
    caller: Caller | None = None,
    root: Path | None = None,
) -> bool:
    """Exécute une tâche prête. Faux si elle n'était plus prête.

    En cas d'erreur, l'exception remonte : c'est à l'appelant d'annuler
    les écritures de la tâche, puis de la marquer en échec.
    """
    if not start_task(conn, task_id):
        return False
    # La tâche est marquée « en cours » et enregistrée tout de suite : la
    # base n'est jamais bloquée pendant un appel au modèle.
    conn.commit()
    row = conn.execute(
        'SELECT invocation_id FROM tasks WHERE id=?', (task_id,)
    ).fetchone()
    inv = load_invocation(conn, str(row[0]))
    task = task_params(conn, task_id)
    if inv.type == 'llm':
        answer = _llm_answer(
            conn, inv, task_id, task, caller=caller, root=root
        )
    else:
        answer = _capability_answer(conn, inv, task)
    written = write_answer(conn, inv.id, task_id, task, answer)
    fire_row_triggers(conn, written)
    pass_links(conn, inv.id, task_id, written)
    finish_task(conn, task_id)
    append_event(
        conn,
        actor=f'invocation:{inv.id}',
        type='task.done',
        payload={
            'task': task_id,
            'rows_written': sum(len(w.rows) for w in written.values()),
        },
    )
    return True


def fail_task(conn: sqlite3.Connection, task_id: str, error: str) -> None:
    """Marque une tâche en échec, avec la raison, et le note au journal."""
    finish_task(conn, task_id, error=error)
    row = conn.execute(
        'SELECT invocation_id FROM tasks WHERE id=?', (task_id,)
    ).fetchone()
    append_event(
        conn,
        actor=f'invocation:{row[0] if row else "?"}',
        type='task.failed',
        payload={'task': task_id, 'error': error[:500]},
    )
