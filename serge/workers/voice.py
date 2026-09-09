#!/usr/bin/env python3
"""Worker voice.score : transcription → score_call → gate qualité.

Retourne pause quand F4c déclenche (FYI/ticket par l'appelant/runner).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.summaries import score_call
from serge.voice.quality import check_voice_quality, record_call_score


def run_score(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    item: Mapping[str, Any],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """Exécute un work_item voice.score (réclamé au préalable).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (seuils F4c).
        item: Work_item (payload cdr_id/transcript/metadata).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict status done (+ note, gate, fallback).
    """
    try:
        payload = json.loads(item.get('payload_json') or '{}')
    except (TypeError, ValueError):
        return {'status': 'error', 'error': 'payload_invalide'}
    cdr_id = str((payload or {}).get('cdr_id') or '')
    transcript = str((payload or {}).get('transcript') or '')
    if not cdr_id or not transcript:
        return {'status': 'error', 'error': 'cdr_ou_transcript_manquant'}
    scored = score_call(
        conn,
        policy,
        transcript,
        str(payload.get('metadata') or ''),
        root=root,
        caller=caller,
    )
    record_call_score(
        conn, cdr_id, scored['note'], scored['flags'], scored['ecouter']
    )
    gate = check_voice_quality(conn, policy)
    return {
        'status': 'done',
        'note': scored['note'],
        'gate': gate['action'],
        'fallback': scored['fallback'],
    }
