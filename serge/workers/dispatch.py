#!/usr/bin/env python3
"""Dispatch workers par kind (kinds inconnus = erreur routable)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.workers.call import run_voice_send
from serge.workers.classify import run_classify
from serge.workers.listen import run_cluster, run_collect
from serge.workers.memory import run_apply, run_consolidate_worker
from serge.workers.poll import run_email_poll
from serge.workers.respond import run_judge_other, run_reply
from serge.workers.send import run_email_send
from serge.workers.voice import run_score

HANDLERS = {
    'inbound.classify': run_classify,
    'inbound.reply_priority': run_reply,
    'inbound.judge_other': run_judge_other,
    'memory.consolidate': run_consolidate_worker,
    'memory.apply': run_apply,
    'listen.collect': run_collect,
    'listen.cluster': run_cluster,
    'voice.score': run_score,
    'email.send': run_email_send,
    'voice.send': run_voice_send,
    'email.poll': run_email_poll,
}


def execute(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item réclamé (complete/fail par l'appelant RUNNER).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy.
        item: Work_item (kind requis).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Résultat du worker (status done|error).
    """
    handler = HANDLERS.get(str(item.get('kind') or ''))
    if handler is None:
        return {
            'status': 'error',
            'error': f'kind_inconnu:{item.get("kind")}',
        }
    return handler(conn, policy, item, root=root, caller=caller)
