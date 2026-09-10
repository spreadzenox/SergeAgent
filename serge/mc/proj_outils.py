#!/usr/bin/env python3
"""Projecteurs MC : micro-outils partagés (3e usage → factorisé ici)."""

from __future__ import annotations

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
