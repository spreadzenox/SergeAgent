#!/usr/bin/env python3
"""Projecteurs MC : micro-outils partagés (3e usage → factorisé ici)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta


def avant_iso(now_iso: str, **duree: int) -> str:
    """ISO décalé dans le passé (fenêtres 24 h / 7 j des projecteurs).

    Args:
        now_iso: Maintenant ISO.
        duree: Durée timedelta (hours=24, minutes=30...).

    Returns:
        Horodatage ISO décalé.
    """
    moment = datetime.fromisoformat(now_iso)
    return (moment - timedelta(**duree)).isoformat()


def apres_iso(now_iso: str, **duree: int) -> str:
    """ISO décalé dans le futur (seuils urgents...).

    Args:
        now_iso: Maintenant ISO.
        duree: Durée timedelta (minutes=15...).

    Returns:
        Horodatage ISO décalé.
    """
    moment = datetime.fromisoformat(now_iso)
    return (moment + timedelta(**duree)).isoformat()


def charge_json(payload_json: object) -> dict:
    """Parse un payload JSON (fail-soft {} si absent/invalide/non-dict).

    Args:
        payload_json: Chaîne JSON (ou autre).

    Returns:
        Le dict parsé, {} sinon.
    """
    if not isinstance(payload_json, str):
        return {}
    try:
        payload = json.loads(payload_json or '{}')
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}
