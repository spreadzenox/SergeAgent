#!/usr/bin/env python3
"""Point O2 : extract_meeting (LLM-1, T1). Creneau + verif det."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from serge.points.jsonio import run_json
from serge.policy import PolicyError

MEETING_SYSTEM = """Tu extrais une proposition de rendez-vous d'un message (français/anglais).
Réponds UNIQUEMENT un objet JSON : {"datetime_iso": "YYYY-MM-DDTHH:MM:SS+02:00 ou null", "duree_min": 30, "moyen": "appel|visio|presentiel|inconnu", "confiance": 0.0-1.0, "ambigu": true|false}.
datetime_iso = le créneau proposé (fuseau Europe/Paris), null si aucun créneau concret. ambigu = true si plusieurs interprétations possibles."""


def _valid_meeting(data: dict[str, Any]) -> bool:
    if data.get('moyen') not in {'appel', 'visio', 'presentiel', 'inconnu'}:
        return False
    try:
        confiance = float(data.get('confiance', -1))
        duree = int(data.get('duree_min', 0))
    except (TypeError, ValueError):
        return False
    if not 0.0 <= confiance <= 1.0 or duree <= 0:
        return False
    raw = data.get('datetime_iso')
    if raw is not None:
        try:
            datetime.fromisoformat(str(raw))
        except ValueError:
            return False
    return isinstance(data.get('ambigu'), bool)


def _biz_hours_ok(policy: Mapping[str, Any], moment: datetime) -> bool:
    try:
        windows = policy.get('windows') or {}
        slots = windows.get('intent_biz_hours', [[8, 0, 20, 0]])
        paris = moment.astimezone(ZoneInfo('Europe/Paris'))
    except (TypeError, ValueError):
        return False
    if paris.weekday() >= 5:
        return False
    for slot in slots:
        try:
            start_h, start_m, end_h, end_m = (int(v) for v in slot)
        except (TypeError, ValueError):
            continue
        if (
            (start_h, start_m)
            <= (paris.hour, paris.minute)
            < (
                end_h,
                end_m,
            )
        ):
            return True
    return False


def extract_meeting(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    message: str,
    *,
    now_iso: str = '',
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """O2 : extrait un créneau + vérif dét (futur, heures ouvrées).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (meeting_confidence_min, intent_biz_hours).
        message: Texte brut.
        now_iso: Maintenant ISO (défaut : UTC actuel, injectable en test).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict datetime_iso/duree_min/moyen/confiance/ambigu/action/fallback.
        action = propose_booking | clarify (jamais de booking deviné).
    """
    try:
        threshold = float(
            (policy.get('observation') or {}).get(
                'meeting_confidence_min', 0.8
            )
        )
    except (TypeError, ValueError) as exc:
        raise PolicyError('policy.meeting_confidence_min invalide') from exc
    now = now_iso or datetime.now().astimezone().isoformat()
    messages = [
        {'role': 'system', 'content': MEETING_SYSTEM},
        {
            'role': 'user',
            'content': f'Maintenant (Europe/Paris) : {now}\nMessage : {message[:800]}',
        },
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 200}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn, policy, 'extract_meeting', messages, _valid_meeting, **kwargs
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'datetime_iso': None,
            'duree_min': 30,
            'moyen': 'inconnu',
            'confiance': 0.0,
            'ambigu': True,
            'action': 'clarify',
            'fallback': reason or 'parse',
        }
    raw = data.get('datetime_iso')
    confiance = float(data['confiance'])
    ambigu = bool(data.get('ambigu'))
    slot_ok = False
    if raw and not ambigu and confiance >= threshold:
        try:
            moment = datetime.fromisoformat(str(raw))
            current = datetime.fromisoformat(now)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=current.tzinfo)
            slot_ok = moment > current and _biz_hours_ok(policy, moment)
        except ValueError:
            slot_ok = False
    return {
        'datetime_iso': str(raw) if raw and slot_ok else None,
        'duree_min': int(data['duree_min']),
        'moyen': str(data['moyen']),
        'confiance': confiance,
        'ambigu': ambigu or not slot_ok,
        'action': 'propose_booking' if slot_ok else 'clarify',
        'fallback': '',
    }
