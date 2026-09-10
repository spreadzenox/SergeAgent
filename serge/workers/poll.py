#!/usr/bin/env python3
"""Worker email.poll : backend actif → ingest ROUTER (dédup message_id).

Recherche (syntaxe du backend), lecture complète, extraction From/corps,
match contact par email, ingest RECEIVED. Erreur search = fatale ;
erreur message = ignorée + comptée. Dédup persistante (message_id).
"""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from serge.channels import MailError, get_message, search_emails
from serge.observe.router import ingest

DEFAULT_QUERY = 'newer_than:1d -in:sent'


def _headers(message: Mapping[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    payload = message.get('payload') if isinstance(message, dict) else None
    headers = (
        (payload or {}).get('headers') if isinstance(payload, dict) else None
    )
    if isinstance(headers, list):
        for item in headers:
            if isinstance(item, dict) and item.get('name'):
                found[str(item['name']).lower()] = str(item.get('value') or '')
    return found


def _walk_text(node: Any) -> str:
    if isinstance(node, dict):
        mime = str(node.get('mimeType') or '')
        body = node.get('body') or {}
        data = body.get('data') if isinstance(body, dict) else None
        if mime.startswith('text/plain') and isinstance(data, str) and data:
            try:
                padded = data + '=' * (-len(data) % 4)
                return base64.urlsafe_b64decode(padded).decode(
                    'utf-8', errors='replace'
                )
            except (ValueError, OSError):
                return ''
        texts = [
            _walk_text(part)
            for part in (node.get('parts') or [])
            if _walk_text(part)
        ]
        return '\n'.join(texts)
    return ''


def _message_text(message: Mapping[str, Any]) -> str:
    payload = message.get('payload')
    text = _walk_text(payload) if isinstance(payload, dict) else ''
    return text.strip() or str(message.get('snippet') or '').strip()


def _match_contact(conn: sqlite3.Connection, from_header: str) -> str:
    import re

    match = re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}', from_header)
    if not match:
        return ''
    row = conn.execute(
        'SELECT id FROM contacts WHERE lower(email)=?',
        (match.group(0).lower(),),
    ).fetchone()
    return str(row[0]) if row else ''


def _seen(conn: sqlite3.Connection, message_id: str) -> bool:
    row = conn.execute(
        'SELECT 1 FROM inbound_events WHERE json_extract(payload_json,'
        "'$.message_id')=? OR json_extract(payload_json, '$.gmail_id')=?",
        (message_id, message_id),
    ).fetchone()
    return row is not None


def run_email_poll(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
    searcher: Callable[..., list[dict[str, Any]]] = search_emails,
    getter: Callable[..., dict[str, Any]] = get_message,
) -> dict[str, Any]:
    """Exécute un work_item email.poll (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (routeur).
        item: Work_item (payload account/query/max_results).
        root: Inutilisé (contrat workers).
        caller: Inutilisé (zéro LLM).
        searcher: Recherche email (injectable).
        getter: Lecture message (injectable).

    Returns:
        Dict status done|error (+ new, skipped).
    """
    del root, caller
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    payload = payload if isinstance(payload, dict) else {}
    account = str(payload.get('account') or 'auto')
    query = str(payload.get('query') or DEFAULT_QUERY)
    try:
        max_results = int(payload.get('max_results', 20))
    except (TypeError, ValueError):
        max_results = 20
    try:
        found = searcher(query, account=account, max_results=max_results)
    except MailError as exc:
        return {'status': 'error', 'error': f'recherche:{exc}'}
    fresh = 0
    skipped = 0
    for entry in found:
        message_id = str(entry.get('id') or '')
        if not message_id or _seen(conn, message_id):
            skipped += 1
            continue
        try:
            message = getter(message_id, account=account)
        except MailError:
            skipped += 1
            continue
        headers = _headers(message)
        text = _message_text(message)
        if not text:
            skipped += 1
            continue
        contact_id = _match_contact(conn, headers.get('from', ''))
        ingest(
            conn,
            policy,
            {
                'channel': 'email',
                'native_type': 'RECEIVED',
                'contact_id': contact_id,
                'campaign_id': '',
                'subject': headers.get('from', ''),
                'venture_id': str(item.get('venture_id') or ''),
                'payload': {
                    'text': text[:4000],
                    'message_id': message_id,
                    'subject': headers.get('subject', '')[:200],
                },
            },
        )
        fresh += 1
    return {'status': 'done', 'new': fresh, 'skipped': skipped}
