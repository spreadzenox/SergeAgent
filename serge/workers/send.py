#!/usr/bin/env python3
"""Workers d'envoi : email.send (P2/P3 + guards + quota + touch).

Rendu : draft fourni (réponse) ou P2 template (step 0) ou P3 followup.
Guards re-vérifiés à l'envoi + quota mailbox/jour (retry lendemain 8h).
Touch enregistrée (idempotente), contact avancé si QUALIFIED.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from serge.channels import MailError, send_email
from serge.funnels import contacts as contact_mod
from serge.funnels.campaigns import thresholds as campaign_thresholds
from serge.guards import check
from serge.points.write import fill_slots, write_followup


def _payload(item: Mapping[str, Any]) -> dict[str, Any]:
    try:
        data = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _contact_row(
    conn: sqlite3.Connection, contact_id: str
) -> dict[str, Any] | None:
    row = conn.execute(
        'SELECT id, display, email, phone, funnel_state FROM contacts'
        ' WHERE id=?',
        (contact_id,),
    ).fetchone()
    if not row:
        return None
    return {
        'id': row[0],
        'display': row[1],
        'email': row[2],
        'phone': row[3],
        'funnel_state': row[4],
    }


def _fiche_text(contact: Mapping[str, Any]) -> str:
    return (
        f'nom={contact.get("display") or ""} '
        f'email={contact.get("email") or ""}'.strip()
    )


def _thread_history(conn: sqlite3.Connection, contact_id: str) -> str:
    rows = conn.execute(
        'SELECT signal, payload_json FROM inbound_events'
        ' WHERE contact_id=? ORDER BY received_at DESC LIMIT 5',
        (contact_id,),
    ).fetchall()
    lines: list[str] = []
    for signal, raw in rows:
        try:
            text = str((json.loads(raw or '{}') or {}).get('text') or '')
        except (TypeError, ValueError):
            text = ''
        lines.append(f'[{signal}] {text[:200]}')
    return '\n'.join(reversed(lines))


def _sent_today(conn: sqlite3.Connection, day: str) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM touches WHERE channel='email'"
        " AND status='sent' AND created_at LIKE ?",
        (f'{day}%',),
    ).fetchone()
    return int(row[0]) if row else 0


def run_email_send(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
    sender: Callable[..., dict[str, str]] = send_email,
    now: str | None = None,
) -> dict[str, Any]:
    """Exécute un work_item email.send (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (guards + quota mailbox).
        item: Work_item (contact_id, campaign_id, draft|template, step...).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).
        sender: Transport (défaut : backend actif, injectable en test).
        now: ISO (défaut : maintenant, tests).

    Returns:
        Dict status done|error|retry (+ touch_id, error, retry_at).
    """
    from serge.db.store import utcnow

    moment = now or utcnow()
    payload = _payload(item)
    contact_id = str(payload.get('contact_id') or item.get('contact_id') or '')
    contact = _contact_row(conn, contact_id)
    if contact is None or not contact['email']:
        return {'status': 'error', 'error': 'destinataire_inconnu'}
    campaign_id = str(
        payload.get('campaign_id') or item.get('campaign_id') or ''
    )
    try:
        camp_thresholds = (
            campaign_thresholds(conn, campaign_id) if campaign_id else {}
        )
    except ValueError:
        camp_thresholds = {}
    subject = str(
        payload.get('subject') or camp_thresholds.get('subject') or ''
    )
    if not subject:
        return {'status': 'error', 'error': 'sujet_manquant'}
    draft = str(payload.get('draft') or '')
    if not draft:
        step = int(payload.get('step', 0) or 0)
        if step <= 0:
            template = str(
                payload.get('template')
                or camp_thresholds.get('template')
                or ''
            )
            if not template:
                return {'status': 'error', 'error': 'template_manquant'}
            rendered = fill_slots(
                conn,
                policy,
                template,
                _fiche_text(contact),
                root=root,
                caller=caller,
            )
            draft = rendered['text']
        else:
            rendered = write_followup(
                conn,
                policy,
                _thread_history(conn, contact['id']),
                root=root,
                caller=caller,
            )
            draft = rendered['text']
    item_key = str(item.get('idempotency_key') or item.get('id'))
    verdict = check(
        conn,
        policy,
        {
            'channel': 'email',
            'subject': contact['email'],
            'idempotency_key': f'send:{item_key}',
            'contact_id': contact['id'],
        },
        moment,
    )
    if not verdict.allowed:
        return {
            'status': 'error',
            'error': f'guards:{verdict.reason.value}',
        }
    quotas = policy.get('quotas') or {}
    try:
        mailbox_cap = int(quotas.get('email_per_mailbox_per_day', 40))
    except (TypeError, ValueError):
        mailbox_cap = 40
    if _sent_today(conn, moment[:10]) >= max(1, mailbox_cap):
        tomorrow = (datetime.fromisoformat(moment) + timedelta(days=1)).date()
        return {
            'status': 'retry',
            'retry_at': f'{tomorrow}T08:00:00+00:00',
            'error': 'quota_mailbox',
        }
    try:
        sent = sender(
            contact['email'],
            subject,
            draft,
            thread_id=str(payload.get('thread_id') or ''),
        )
    except MailError as exc:
        return {'status': 'error', 'error': f'envoi:{exc}'}
    touch_id = f't_{abs(hash(("email", item_key))) % 10**12:012d}'
    conn.execute(
        'INSERT OR IGNORE INTO touches(id, campaign_id, contact_id,'
        ' channel, kind, status, cost_eur, idempotency_key, created_at,'
        ' updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
        (
            touch_id,
            campaign_id,
            contact['id'],
            'email',
            'reply' if payload.get('in_reply_to') else 'send',
            'sent',
            0.0,
            f'touch:{item_key}',
            moment,
            moment,
        ),
    )
    if contact['funnel_state'] == 'QUALIFIED':
        try:
            contact_mod.start_contacting(conn, contact['id'])
        except contact_mod.ContactError:
            pass
    return {
        'status': 'done',
        'touch_id': touch_id,
        'message_id': sent.get('message_id', ''),
    }
