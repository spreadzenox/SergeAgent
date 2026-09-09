#!/usr/bin/env python3
"""Worker voice.send : originate gaté broker (idempotent par item).

Le broker décide (mandat, consentement, quotas, fenêtres, NPV) ; refus =
erreur routable (déjà loggée broker) ; trunk KO = erreur ; doublon =
done (rejeu prouvé). Jamais de dial hors broker.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from serge.voice.bridge import originate
from serge.voice.policy import VoiceBrokerDenied


def run_voice_send(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
    originator: Callable[..., dict[str, Any]] = originate,
) -> dict[str, Any]:
    """Exécute un work_item voice.send (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (non lue, contrat uniforme ; broker autonome).
        item: Work_item (contact_id, pitch optionnel).
        root: Inutilisé (contrat workers).
        caller: Inutilisé (zéro LLM).
        originator: Fonction originate (injectable en test).

    Returns:
        Dict status done|error (+ cdr_id, reason, duplicate).
    """
    del policy, root, caller
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    contact_id = str(
        (payload or {}).get('contact_id') or item.get('contact_id') or ''
    )
    phone = ''
    if contact_id:
        row = conn.execute(
            'SELECT phone FROM contacts WHERE id=?', (contact_id,)
        ).fetchone()
        phone = str(row[0] or '') if row else ''
    if not phone:
        return {'status': 'error', 'error': 'telephone_inconnu'}
    item_id = str(item.get('id') or '')
    try:
        result = originator(
            request_id=f'req_{item_id}',
            to_e164=phone,
            purpose='prospection',
            task_id=item_id,
            message=str((payload or {}).get('pitch') or ''),
        )
    except VoiceBrokerDenied as exc:
        return {'status': 'error', 'error': f'broker:{exc}'}
    if result.get('decision') != 'allowed':
        return {
            'status': 'error',
            'error': f'broker:{result.get("reason", "denied")}',
        }
    if result.get('duplicate'):
        return {
            'status': 'done',
            'cdr_id': str(result.get('cdr_id') or ''),
            'duplicate': True,
        }
    if not result.get('originated'):
        return {
            'status': 'error',
            'error': f'trunk:{result.get("error", "originate_failed")}',
        }
    return {'status': 'done', 'cdr_id': str(result.get('cdr_id') or '')}
