#!/usr/bin/env python3
"""Point P7 : score_lead (score déterministe + départage LLM en zone grise).

Le score vient des compteurs de signaux (barème policy). L'invocation LLM
n'est appelée qu'en zone grise et si la décision coûte cher. Repli : score
déterministe seul.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

DEPARTAGE_SYSTEM = """Tu départages un prospect en zone grise (français).
Réponds UNIQUEMENT un objet JSON : {"decision": "allouer|abandonner", "confiance": 0.0-1.0, "motif": "..."}.
allouer = vaut un appel/suivi humain ; abandonner = stopper les frais. Tiens compte de l'historique et du coût d'opportunité."""


def det_score(
    conn: sqlite3.Connection, policy: Mapping[str, Any], contact_id: str
) -> dict[str, Any]:
    """P7 DET : score 0-100 depuis compteurs signaux (barème policy).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (prospection.score_w_* + lead_score_gray).
        contact_id: Contact scoré.

    Returns:
        Dict score/zone (low|gray|high)/decision DET (revoir si gray).
    """
    section = policy.get('prospection') or {}
    weights = {
        'INTENT': float(section.get('score_w_intent', 25)),
        'REPLIED': float(section.get('score_w_reply', 10)),
        'ENGAGED': float(section.get('score_w_engaged', 5)),
        'MEETING': float(section.get('score_w_meeting', 40)),
        'NEGATIVE': float(section.get('score_w_negative', -20)),
    }
    rows = conn.execute(
        'SELECT signal, class, COUNT(*) FROM inbound_events'
        ' WHERE contact_id=? GROUP BY signal, class',
        (contact_id,),
    ).fetchall()
    total = 0.0
    for signal, cls, count in rows:
        total += weights.get(str(signal), 0.0) * int(count)
        if str(cls) == 'MEETING_REQUEST':
            total += weights['MEETING'] * int(count)
    score = max(0, min(100, int(round(total))))
    gray = section.get('lead_score_gray', [40, 60])
    try:
        low, high = int(gray[0]), int(gray[1])
    except (TypeError, ValueError, IndexError):
        low, high = 40, 60
    if score < low:
        return {'score': score, 'zone': 'low', 'decision': 'abandonner'}
    if score > high:
        return {'score': score, 'zone': 'high', 'decision': 'allouer'}
    return {'score': score, 'zone': 'gray', 'decision': 'revoir'}


def _valid_departage(data: dict[str, Any]) -> bool:
    if data.get('decision') not in {'allouer', 'abandonner'}:
        return False
    try:
        confiance = float(data.get('confiance', -1))
    except (TypeError, ValueError):
        return False
    return 0.0 <= confiance <= 1.0


def score_lead(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    contact_id: str,
    history_text: str = '',
    *,
    costly: bool = False,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """P7 : score DET + départage LLM-1 si zone grise + décision coûteuse.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (barème + zone grise).
        contact_id: Contact scoré.
        history_text: Résumé historique (départage seul).
        costly: Décision coûteuse (appel humain...) ?
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict score/zone/decision (+ motif, fallback si LLM tenté).
    """
    base = det_score(conn, policy, contact_id)
    if base['zone'] != 'gray' or not costly:
        return {**base, 'motif': '', 'fallback': ''}
    messages = [
        {'role': 'system', 'content': DEPARTAGE_SYSTEM},
        {
            'role': 'user',
            'content': f'Score DET : {base["score"]} (zone grise).'
            f'\nHistorique : {history_text[:1500]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'score_lead_departage',
        messages,
        _valid_departage,
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {**base, 'motif': '', 'fallback': reason or 'parse'}
    return {
        'score': base['score'],
        'zone': 'gray',
        'decision': str(data['decision']),
        'motif': str(data.get('motif') or ''),
        'fallback': '',
    }
