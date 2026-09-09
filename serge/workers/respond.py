#!/usr/bin/env python3
"""Workers inbound.reply_priority + inbound.judge_other (O3, O4).

Réponse : O3 → send (guards + file {canal}.send) ou ticket QNA (doute,
filets, refus guards). Juge : O4 → reclassements appliqués + proposition
→ ticket QNA. Tickets publiés (OPEN) pour l'owner.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.guards import check
from serge.points.other import review_other_batch
from serge.points.reply import draft_intent_reply
from serge.registry import load_ticket_types
from serge.scheduler import enqueue
from serge.tickets import create_ticket, publish

RECLASS_MIN_CONFIDENCE = 0.6


def _payload(item: Mapping[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_event(
    conn: sqlite3.Connection, event_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT id, campaign_id, contact_id, channel, native_type, signal,'
        ' class, received_at, payload_json FROM inbound_events WHERE id=?',
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
        'class',
        'received_at',
        'payload_json',
    )
    return dict(zip(keys, row, strict=True))


def _event_text(event: Mapping[str, Any]) -> str:
    try:
        payload = json.loads(event.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return ''
    if isinstance(payload, dict):
        return str(payload.get('text') or '')
    return ''


def _thread_history(conn: sqlite3.Connection, contact_id: str) -> str:
    if not contact_id:
        return ''
    rows = conn.execute(
        'SELECT signal, class, payload_json FROM inbound_events'
        ' WHERE contact_id=? ORDER BY received_at DESC LIMIT 5',
        (contact_id,),
    ).fetchall()
    lines: list[str] = []
    for signal, cls, raw in rows:
        try:
            payload = json.loads(raw or '{}')
            text = str((payload or {}).get('text') or '')[:200]
        except (TypeError, ValueError):
            text = ''
        lines.append(f'[{signal}/{cls}] {text}')
    return '\n'.join(reversed(lines))


def _subject_for(
    conn: sqlite3.Connection, channel: str, contact_id: str
) -> str:
    if not contact_id:
        return ''
    row = conn.execute(
        'SELECT email, phone FROM contacts WHERE id=?', (contact_id,)
    ).fetchone()
    if not row:
        return ''
    if channel in {'voice', 'sms'}:
        return str(row[1] or '')
    return str(row[0] or '')


def _open_qna(
    conn: sqlite3.Connection,
    title: str,
    question: str,
    context: str,
) -> str:
    types = load_ticket_types()
    ticket_id = create_ticket(
        conn,
        types,
        'QNA',
        title,
        {'question': question, 'options_qcm': [], 'contexte': context},
    )
    publish(conn, ticket_id)
    return ticket_id


def run_reply(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item inbound.reply_priority (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (guards + O3).
        item: Work_item (payload.event_id requis).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done|error (+ action, error).
    """
    payload = _payload(item)
    event = _load_event(conn, str(payload.get('event_id') or ''))
    if event is None:
        return {'status': 'error', 'error': 'evenement_inconnu'}
    channel = str(event['channel'] or '')
    contact_id = str(event['contact_id'] or '')
    subject = _subject_for(conn, channel, contact_id)
    if not subject:
        return {'status': 'error', 'error': 'destinataire_inconnu'}
    classe = str(payload.get('classe') or event['class'] or 'INTENT')
    history = _thread_history(conn, contact_id)
    if payload.get('slot'):
        history += f'\n[Créneau proposé : {payload["slot"]} ({payload.get("moyen", "")})]'
    draft = draft_intent_reply(
        conn,
        policy,
        history,
        classe,
        _event_text(event),
        root=root,
        caller=caller,
    )
    if draft['action'] != 'send':
        ticket_id = _open_qna(
            conn,
            f'Réponse à valider ({classe})',
            'Envoyer ce brouillon ?',
            f'{draft["draft"]}\n\nMotif : {draft["reason"]}',
        )
        return {'status': 'done', 'action': 'ticket', 'ticket_id': ticket_id}
    verdict = check(
        conn,
        policy,
        {
            'channel': channel,
            'subject': subject,
            'idempotency_key': f'reply:{event["id"]}',
            'contact_id': contact_id,
        },
    )
    if not verdict.allowed:
        ticket_id = _open_qna(
            conn,
            f'Réponse bloquée guards ({classe})',
            'Forcer l\u2019envoi ?',
            f'{draft["draft"]}\n\nRefus : {verdict.reason.value}',
        )
        return {'status': 'done', 'action': 'ticket', 'ticket_id': ticket_id}
    enqueue(
        conn,
        kind=f'{channel}.send',
        idempotency_key=f'work:reply-send:{event["id"]}',
        venture_id=str(item.get('venture_id') or ''),
        campaign_id=str(event['campaign_id'] or ''),
        contact_id=contact_id,
        payload={
            'subject': subject,
            'draft': draft['draft'],
            'in_reply_to': event['id'],
        },
    )
    return {'status': 'done', 'action': 'sent_queued'}


def run_judge_other(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item inbound.judge_other (batch OTHER).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (cap batch, seuils).
        item: Work_item (payload.event_ids optionnel, sinon collecte).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done (+ applied, stayed, ticket_id).
    """
    payload = _payload(item)
    wanted = payload.get('event_ids')
    if isinstance(wanted, list) and wanted:
        placeholders = ','.join('?' * len(wanted))
        rows = conn.execute(
            'SELECT id, channel, native_type, payload_json FROM inbound_events'
            f" WHERE id IN ({placeholders}) AND signal='OTHER'",
            [str(item_id) for item_id in wanted],
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, channel, native_type, payload_json FROM inbound_events'
            " WHERE signal='OTHER' ORDER BY received_at ASC LIMIT 20"
        ).fetchall()
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row[3] or '{}')
            text = str((data or {}).get('text') or '')
        except (TypeError, ValueError):
            text = ''
        items.append(
            {
                'id': row[0],
                'channel': row[1],
                'native_type': row[2],
                'excerpt': text[:300],
            }
        )
    if not items:
        return {'status': 'done', 'applied': 0, 'stayed': 0}
    result = review_other_batch(conn, policy, items, root=root, caller=caller)
    applied = 0
    for entry in result['reclass']:
        try:
            confiance = float(entry.get('confiance', 0))
        except (TypeError, ValueError):
            continue
        if confiance < RECLASS_MIN_CONFIDENCE:
            continue
        signal = str(entry.get('signal'))
        conn.execute(
            'UPDATE inbound_events SET signal=? WHERE id=?',
            (signal, str(entry.get('id'))),
        )
        applied += 1
        if signal == 'INTENT':
            enqueue(
                conn,
                kind='inbound.reply_priority',
                idempotency_key=f'work:reply:{entry.get("id")}',
                venture_id=str(item.get('venture_id') or ''),
                payload={'event_id': str(entry.get('id')), 'classe': 'INTENT'},
            )
        elif signal == 'REPLIED':
            enqueue(
                conn,
                kind='inbound.classify',
                idempotency_key=f'work:classify:{entry.get("id")}',
                venture_id=str(item.get('venture_id') or ''),
                payload={'event_id': str(entry.get('id'))},
            )
    ticket_id = ''
    if result['proposition']:
        proposition = result['proposition']
        ticket_id = _open_qna(
            conn,
            f'Catégorie proposée : {proposition.get("nom")}',
            'Ajouter cette catégorie à la taxonomie ?',
            str(proposition.get('definition') or ''),
        )
    return {
        'status': 'done',
        'applied': applied,
        'stayed': len(items) - applied,
        'ticket_id': ticket_id,
    }
