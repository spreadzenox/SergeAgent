#!/usr/bin/env python3
"""Boîte Serge : mail (canon) et SMS (ledger inbox), corps brut."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.sms.inbox import SmsInbox


def lire_boite(
    conn: sqlite3.Connection,
    *,
    sms: SmsInbox | None = None,
    limite: int = 40,
) -> dict[str, Any]:
    """Historique brut mail + SMS.

    Args:
        conn: Canon (inbound_events e-mail).
        sms: Inbox SMS, si le ledger existe.
        limite: Plafond par canal.

    Returns:
        ``mails`` et ``sms`` : listes de messages bruts.
    """
    rows = conn.execute(
        'SELECT received_at, payload_json, contact_id FROM inbound_events'
        " WHERE channel='email' ORDER BY received_at DESC LIMIT ?",
        (limite,),
    ).fetchall()
    mails: list[dict[str, str]] = []
    for recu, brut, contact in rows:
        try:
            payload = json.loads(brut or '{}')
        except json.JSONDecodeError:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        mails.append(
            {
                'heure': str(recu or ''),
                'expediteur': str(payload.get('from') or ''),
                'destinataire': str(payload.get('to') or ''),
                'sujet': str(payload.get('subject') or ''),
                'corps': str(payload.get('text') or ''),
                'contact_id': str(contact or ''),
            }
        )
    textos = sms.messages(limite=limite) if sms is not None else []
    return {'mails': mails, 'sms': textos}
