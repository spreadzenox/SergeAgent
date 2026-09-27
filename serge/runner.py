#!/usr/bin/env python3
"""Runner : un cycle (expiry tickets + file READY + consolidation due).

Boucle : expire_due → consolidation si due (file, idempotente/jour) →
relève mail programmée (une par créneau de windows.email_poll_minutes) →
claim → dispatch.execute → complete | fail | fail+retry_at. Gate voix
pause → FYI. Un commit par cycle (atomicité). Zéro LLM direct.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from serge.coupe_circuit import heartbeat_marche
from serge.db.store import append_event, utcnow
from serge.memory.consolidate import due_for_consolidation
from serge.registry import load_ticket_types
from serge.scheduler import claim, complete, enqueue, fail, next_ready
from serge.tickets import create_ticket, expire_due, publish
from serge.workers.dispatch import execute


def _ensure_consolidation(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> bool:
    if not due_for_consolidation(conn, policy, now):
        return False
    enqueue(
        conn,
        kind='memory.consolidate',
        idempotency_key=f'cron:consolidate:{now[:10]}',
        payload={},
    )
    return True


def _ensure_email_poll(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> None:
    """Programme la relève de la boîte mail, une fois par créneau.

    Exemple : avec ``windows.email_poll_minutes: 5``, une tâche
    ``email.poll`` est créée au plus une fois toutes les 5 minutes.
    """
    windows = policy.get('windows') or {}
    minutes = windows.get('email_poll_minutes', 5)
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        minutes = 5
    seconds = int(datetime.fromisoformat(now).timestamp())
    slot = seconds // (max(1, minutes) * 60)
    enqueue(
        conn,
        kind='email.poll',
        idempotency_key=f'cron:email_poll:{slot}',
        priority=80,
        payload={},
    )


def _quality_fyi(conn: sqlite3.Connection, detail: str) -> None:
    types = load_ticket_types()
    ticket_id = create_ticket(
        conn,
        types,
        'FYI',
        'Qualité voix dégradée (F4c)',
        {'contenu': f'Gate pause : {detail}. Reprise manuelle.'},
    )
    publish(conn, ticket_id)


def run_once(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
    max_items: int = 10,
    now: str | None = None,
) -> dict[str, Any]:
    """Exécute un cycle complet (commit unique en fin).

    Args:
        conn: Connexion canon (commit ici).
        policy: Policy.
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).
        max_items: Cap work_items/cycle.
        now: ISO (défaut : maintenant).

    Returns:
        Dict processed/done/failed/retried/expired/consolidation.
    """
    moment = now or utcnow()
    started = time.monotonic()
    expired = expire_due(conn, moment)
    consolidation = False
    if heartbeat_marche(conn, moment):
        consolidation = _ensure_consolidation(conn, policy, moment)
        _ensure_email_poll(conn, policy, moment)
    done = failed = retried = 0
    processed = 0
    for _ in range(max(1, max_items)):
        item = next_ready(conn, moment)
        if item is None:
            break
        claimed = claim(conn, str(item['id']))
        if claimed is None:
            continue
        processed += 1
        try:
            result = execute(conn, policy, claimed, root=root, caller=caller)
        except Exception as exc:  # noqa: BLE001 — un worker ne tue jamais le cycle
            fail(conn, str(item['id']), f'WORKER_CRASH:{type(exc).__name__}')
            failed += 1
            continue
        status = str(result.get('status') or 'error')
        if status == 'done':
            complete(conn, str(item['id']), result)
            done += 1
            if result.get('gate') == 'pause':
                _quality_fyi(conn, str(result.get('note') or ''))
        elif status == 'retry':
            fail(
                conn,
                str(item['id']),
                str(result.get('error') or 'retry'),
                retry_at=str(result.get('retry_at') or ''),
            )
            retried += 1
        else:
            fail(conn, str(item['id']), str(result.get('error') or 'error'))
            failed += 1
    append_event(
        conn,
        actor='runner',
        type='cycle',
        payload={
            'processed': processed,
            'done': done,
            'failed': failed,
            'retried': retried,
            'expired': len(expired),
            'consolidation': consolidation,
            'duration_ms': int((time.monotonic() - started) * 1000),
        },
    )
    conn.commit()
    return {
        'processed': processed,
        'done': done,
        'failed': failed,
        'retried': retried,
        'expired': len(expired),
        'consolidation': consolidation,
    }
