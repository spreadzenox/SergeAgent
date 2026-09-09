#!/usr/bin/env python3
"""Worker inbound.classify : O1 puis routage (opt-out, meeting, réponse).

REPLIED → O1 → classe stockée → UNSUBSCRIBE/SPAM = OPT_OUT forcé ;
NEGATIVE = NEGATIVE forcé (stop + leçon) ; MEETING_REQUEST = O2 puis
file réponse (avec créneau) ; OBJECTION/QUESTION/POSITIVE = file réponse ;
AUTO/OTHER = fin. Le worker VÉRIFIE et route ; guards/send au bout.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.observe.router import ingest
from serge.points.classify import classify_reply
from serge.points.meeting import extract_meeting
from serge.scheduler import enqueue

REPLY_CLASSES = frozenset(
    {'MEETING_REQUEST', 'OBJECTION', 'QUESTION', 'POSITIVE'}
)


def _event_text(event: Mapping[str, Any]) -> str:
    direct = str(event.get('text') or '').strip()
    if direct:
        return direct
    try:
        payload = json.loads(event.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return ''
    if isinstance(payload, dict):
        return str(payload.get('text') or '')
    return ''


def _load_event(
    conn: sqlite3.Connection, event_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT id, campaign_id, contact_id, channel, native_type, signal,'
        ' received_at, payload_json FROM inbound_events WHERE id=?',
        (event_id,),
    ).fetchone()
    if not row:
        return None
    keys = (
        'id',
        'campaign_id',
        'contact_id',
        'channel',
        'native_type',
        'signal',
        'received_at',
        'payload_json',
    )
    return dict(zip(keys, row, strict=True))


def run_classify(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item inbound.classify (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy.
        item: Work_item (payload.event_id requis).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done|error (+ classe, action, error).
    """
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    event_id = str((payload or {}).get('event_id') or '')
    event = _load_event(conn, event_id) if event_id else None
    if event is None:
        return {'status': 'error', 'error': 'evenement_inconnu'}
    text = _event_text(event)
    if not text:
        return {'status': 'error', 'error': 'texte_vide'}
    result = classify_reply(
        conn,
        policy,
        text,
        context_lines=[f'canal={event["channel"]}'],
        root=root,
        caller=caller,
    )
    classe = str(result['classe'])
    conn.execute(
        'UPDATE inbound_events SET class=? WHERE id=?', (classe, event_id)
    )
    base = {
        'channel': event['channel'],
        'contact_id': event['contact_id'],
        'campaign_id': event['campaign_id'],
        'venture_id': item.get('venture_id') or '',
    }
    if result['opt_out']:
        ingest(conn, policy, {**base, 'signal': 'OPT_OUT', 'text': text})
        return {'status': 'done', 'classe': classe, 'action': 'opt_out'}
    if classe == 'NEGATIVE':
        ingest(conn, policy, {**base, 'signal': 'NEGATIVE', 'text': text})
        return {'status': 'done', 'classe': classe, 'action': 'negative'}
    if classe not in REPLY_CLASSES:
        return {'status': 'done', 'classe': classe, 'action': 'none'}
    extra: dict[str, Any] = {'event_id': event_id, 'classe': classe}
    if classe == 'MEETING_REQUEST':
        meeting = extract_meeting(conn, policy, text, root=root, caller=caller)
        if meeting['action'] == 'propose_booking':
            extra['slot'] = meeting['datetime_iso']
            extra['moyen'] = meeting['moyen']
    enqueue(
        conn,
        kind='inbound.reply_priority',
        idempotency_key=f'work:reply:{event_id}',
        venture_id=str(item.get('venture_id') or ''),
        campaign_id=str(event['campaign_id'] or ''),
        contact_id=str(event['contact_id'] or ''),
        priority=100,
        payload=extra,
    )
    return {'status': 'done', 'classe': classe, 'action': 'reply_queued'}
