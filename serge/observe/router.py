#!/usr/bin/env python3
"""Routeur universel (B §4 couche 3) : aveugle au canal, déterministe.

ingest() stocke l'événement normalisé puis route : TECH_FAIL (pattern →
alert), REPLIED (→ classify), INTENT (prioritaire + attribution +
régime + état), NEGATIVE (stop + leçon candidate), OPT_OUT (blocage
canal+global + état, P0), OTHER (→ juge batch). Files LLM = work_items
(workers phase 3 ; rien n'est perdu en attendant).
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import append_event, utcnow
from serge.funnels.contacts import (
    ContactError,
    mark_intent,
    mark_invalid,
    mark_unreachable,
    note_inbound,
    opt_out,
    start_contacting,
)
from serge.observe.normalize import normalize
from serge.observe.signals import Signal
from serge.privacy import subject_hash
from serge.scheduler import enqueue


def _new_id() -> str:
    return f'e_{uuid.uuid4().hex[:12]}'


def _store(
    conn: sqlite3.Connection,
    event: Mapping[str, Any],
    signal: Signal,
    now: str,
) -> str:
    event_id = str(event.get('id') or _new_id())
    conn.execute(
        'INSERT OR IGNORE INTO inbound_events(id, campaign_id, contact_id,'
        ' channel, native_type, signal, class, score, cost_eur,'
        ' received_at, payload_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (
            event_id,
            str(event.get('campaign_id') or ''),
            str(event.get('contact_id') or ''),
            str(event.get('channel') or ''),
            str(event.get('native_type') or ''),
            signal.value,
            str(event.get('class') or ''),
            float(event.get('score') or 0),
            float(event.get('cost') or 0),
            str(event.get('received_at') or now),
            json.dumps(event.get('payload') or {}, ensure_ascii=False),
        ),
    )
    return event_id


def _tech_failures_since(
    conn: sqlite3.Connection, channel: str, since: str
) -> int:
    row = conn.execute(
        'SELECT COUNT(*) FROM inbound_events WHERE channel=?'
        " AND signal='TECH_FAIL' AND received_at>=?",
        (channel, since),
    ).fetchone()
    return int(row[0]) if row else 0


def _recent_touches(
    conn: sqlite3.Connection, contact_id: str, since: str
) -> list[str]:
    if not contact_id:
        return []
    rows = conn.execute(
        'SELECT id FROM touches WHERE contact_id=?'
        " AND status IN ('sent','delivered') AND created_at>=?"
        ' ORDER BY created_at DESC LIMIT 10',
        (contact_id, since),
    ).fetchall()
    return [str(row[0]) for row in rows]


def _block_subject(
    conn: sqlite3.Connection, channel: str, subject: str, now: str
) -> None:
    digest = subject_hash(subject)
    for scope in (channel, '*'):
        conn.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, subject_ref,'
            ' reason, added_at) VALUES(?,?,?,?,?,?)'
            ' ON CONFLICT(channel, subject_hash) DO NOTHING',
            (
                f'{scope}_{digest[:16]}',
                scope,
                digest,
                subject,
                'opt_out',
                now,
            ),
        )


def _progress_on_intent(conn: sqlite3.Connection, contact_id: str) -> None:
    if not contact_id:
        return
    row = conn.execute(
        'SELECT funnel_state FROM contacts WHERE id=?', (contact_id,)
    ).fetchone()
    if not row:
        return
    state = str(row[0])
    try:
        if state == 'QUALIFIED':
            start_contacting(conn, contact_id)
            mark_intent(conn, contact_id)
        elif state in {'CONTACTING', 'ENGAGED'}:
            mark_intent(conn, contact_id)
    except ContactError:
        pass


def ingest(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    event: Mapping[str, Any],
    now: str | None = None,
) -> dict[str, Any]:
    """Stocke + route un événement natif. Retourne {id, signal, actions}.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (seuil pattern TECH_FAIL).
        event: channel, native_type (+ campaign_id, contact_id, subject,
            class, score, cost, received_at, payload).
        now: ISO UTC (défaut : maintenant).

    Returns:
        Dict avec id, signal et codes d'actions exécutées.
    """
    moment = now or utcnow()
    channel = str(event.get('channel') or '')
    forced = str(event.get('signal') or '')
    if forced:
        try:
            signal = Signal(forced)
        except ValueError:
            signal = Signal.OTHER
    else:
        signal = normalize(channel, str(event.get('native_type') or ''))
    event_id = _store(conn, event, signal, moment)
    contact_id = str(event.get('contact_id') or '')
    subject = str(event.get('subject') or '')
    venture_id = str(event.get('venture_id') or '')
    actions: list[str] = []
    pattern_per_week = int(
        (policy.get('observation') or {}).get('tech_fail_pattern_per_week', 3)
    )
    if signal == Signal.TECH_FAIL:
        actions.append('health_log')
        since = (
            datetime.fromisoformat(moment) - timedelta(days=7)
        ).isoformat()
        if _tech_failures_since(conn, channel, since) >= pattern_per_week:
            actions.append('alert')
            append_event(
                conn,
                actor='router',
                type='alert.tech_fail_pattern',
                venture_id=venture_id,
                payload={'channel': channel, 'event': event_id},
            )
        if contact_id and str(event.get('native_type')) in {
            'BOUNCED',
            'NUMBER_INVALID',
        }:
            try:
                mark_invalid(conn, contact_id, str(event.get('native_type')))
                actions.append('contact_invalid')
            except ContactError:
                pass
    elif signal in {Signal.SEEN, Signal.ENGAGED, Signal.TECH_OK}:
        pass
    elif signal == Signal.REPLIED:
        if contact_id:
            note_inbound(conn, contact_id, moment)
        enqueue(
            conn,
            kind='inbound.classify',
            idempotency_key=f'work:classify:{event_id}',
            venture_id=venture_id,
            campaign_id=str(event.get('campaign_id') or ''),
            contact_id=contact_id,
            payload={'event_id': event_id},
        )
        actions.append('classify')
    elif signal == Signal.INTENT:
        if contact_id:
            note_inbound(conn, contact_id, moment)
            _progress_on_intent(conn, contact_id)
        since = (
            datetime.fromisoformat(moment) - timedelta(days=30)
        ).isoformat()
        append_event(
            conn,
            actor='router',
            type='attribution.intent',
            venture_id=venture_id,
            payload={'event': event_id},
            links={'touches': _recent_touches(conn, contact_id, since)},
        )
        enqueue(
            conn,
            kind='inbound.reply_priority',
            idempotency_key=f'work:reply:{event_id}',
            venture_id=venture_id,
            campaign_id=str(event.get('campaign_id') or ''),
            contact_id=contact_id,
            priority=100,
            payload={'event_id': event_id},
        )
        actions.append('reply_priority')
    elif signal == Signal.NEGATIVE:
        if contact_id:
            try:
                mark_unreachable(conn, contact_id)
                actions.append('contact_stopped')
            except ContactError:
                pass
        append_event(
            conn,
            actor='router',
            type='lesson.candidate',
            venture_id=venture_id,
            payload={'event': event_id, 'kind': 'negative'},
        )
        actions.append('lesson_candidate')
    elif signal == Signal.OPT_OUT:
        if subject:
            _block_subject(conn, channel, subject, moment)
            actions.append('blocked')
        if contact_id:
            try:
                opt_out(conn, contact_id)
                actions.append('contact_opted_out')
            except ContactError:
                pass
        append_event(
            conn,
            actor='router',
            type='alert.opt_out',
            venture_id=venture_id,
            payload={'event': event_id, 'channel': channel},
        )
        actions.append('alert')
    else:
        enqueue(
            conn,
            kind='inbound.judge_other',
            idempotency_key=f'work:other:{event_id}',
            venture_id=venture_id,
            campaign_id=str(event.get('campaign_id') or ''),
            contact_id=contact_id,
            payload={'event_id': event_id},
        )
        actions.append('judge_other')
    return {'id': event_id, 'signal': signal.value, 'actions': actions}
