#!/usr/bin/env python3
"""Qualité voix F4c : scores post-appel + gate (2 mauvaises/10 → pause).

Scores = événements call.scored (note 1-5 + flags + écouter). Gate dét
sur fenêtre glissante (policy). Pause = alerte + FYI par l'appelant
(jamais de coupure silencieuse, jamais d'auto-reprise).
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from serge.db.store import append_event
from serge.policy import PolicyError


def record_call_score(
    conn: sqlite3.Connection,
    cdr_id: str,
    note: int | None,
    flags: Sequence[str],
    ecouter: bool,
) -> None:
    """Enregistre un score d'appel (pas de score = non noté, explicite).

    Args:
        conn: Connexion canon (commit par l'appelant).
        cdr_id: Id CDR voix.
        note: 1-5 ou None (repli point).
        flags: Flags à réécouter.
        ecouter: File écoute owner ?
    """
    append_event(
        conn,
        actor='quality',
        type='call.scored',
        payload={
            'cdr': cdr_id,
            'note': note,
            'flags': list(flags),
            'ecouter': ecouter,
        },
    )


def recent_scores(
    conn: sqlite3.Connection, window: int
) -> list[dict[str, Any]]:
    """Derniers scores notés (fenêtre glissante, None exclus).

    Args:
        conn: Connexion canon (lecture).
        window: Taille fenêtre (policy).

    Returns:
        Scores [{cdr, note, flags, ecouter}] (récents d'abord).
    """
    rows = conn.execute(
        "SELECT payload_json FROM events WHERE type='call.scored'"
        ' ORDER BY id DESC LIMIT ?',
        (max(1, window) * 2,),
    ).fetchall()
    scored: list[dict[str, Any]] = []
    for row in rows:
        try:
            data = json.loads(row[0] or '{}')
        except (TypeError, ValueError):
            continue
        note = data.get('note')
        if isinstance(note, bool) or not isinstance(note, int):
            continue
        if note not in {1, 2, 3, 4, 5}:
            continue
        scored.append(
            {
                'cdr': str(data.get('cdr') or ''),
                'note': note,
                'flags': list(data.get('flags') or []),
                'ecouter': bool(data.get('ecouter')),
            }
        )
        if len(scored) >= max(1, window):
            break
    return scored


def check_voice_quality(
    conn: sqlite3.Connection, policy: Mapping[str, Any]
) -> dict[str, Any]:
    """Gate F4c : N mauvaises sur fenêtre → pause (alerte appelant).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (voice.quality_window/min_score/max_bad).

    Returns:
        Dict action (ok|pause) + bad/window/seuil.
    """
    section = policy.get('voice') or {}
    try:
        window = int(section.get('quality_window', 10))
        min_score = int(section.get('quality_min_score', 2))
        max_bad = int(section.get('quality_max_bad', 2))
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.voice.quality_* invalide') from exc
    scored = recent_scores(conn, window)
    bad = sum(1 for item in scored if item['note'] <= min_score)
    if bad >= max(1, max_bad):
        return {
            'action': 'pause',
            'bad': bad,
            'window': len(scored),
            'seuil': max_bad,
            'reason': f'{bad} notes ≤{min_score} sur {len(scored)}',
        }
    return {
        'action': 'ok',
        'bad': bad,
        'window': len(scored),
        'seuil': max_bad,
        'reason': '',
    }
