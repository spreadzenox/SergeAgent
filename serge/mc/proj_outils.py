#!/usr/bin/env python3
"""Projecteurs MC : micro-outils partagés (3e usage → factorisé ici)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from typing import Any


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


# Les réactions d'un message reçu qui disent un intérêt (« Traiter une
# réponse », liste fermée du pipeline).
INTERESSE = ('intéressé', 'rendez-vous')


def chiffres_conversations(
    conn: sqlite3.Connection, venture_id: str
) -> dict[str, Any]:
    """Les conversations d'un business, comptées (lot 8).

    ``u1`` : messages partis ; ``u2`` : réponses reçues de ses contacts
    (sans les absences) ; ``u3`` : réponses intéressées (intérêt, rendez-
    vous) ; ``points`` : ses points (grille de points, lot 9) ;
    ``depense_eur`` : ce qu'il a dépensé (modèles et minutes d'appel) ;
    ``points_par_euro`` : ses points par euro dépensé, ``None`` s'il n'a
    rien dépensé ; ``paid`` : euros encaissés.
    """
    from serge.funnels.depense import depense_business, points_par_euro
    from serge.funnels.points import points_business

    def compte(sql: str, *params: str) -> int:
        return int(conn.execute(sql, (venture_id, *params)).fetchone()[0])

    holes = ','.join('?' * len(INTERESSE))
    paid = conn.execute(
        'SELECT COALESCE(SUM(amount_eur), 0) FROM transactions'
        " WHERE venture_id=? AND status='paid'",
        (venture_id,),
    ).fetchone()[0]
    points = points_business(conn, venture_id)
    depense = depense_business(conn, venture_id)['total_eur']
    return {
        'u1': compte(
            "SELECT COUNT(*) FROM touches WHERE venture_id=? AND status='sent'"
        ),
        'u2': compte(
            'SELECT COUNT(*) FROM inbound_events WHERE venture_id=?'
            " AND status='attached' AND reaction<>'absence'"
        ),
        'u3': compte(
            'SELECT COUNT(*) FROM inbound_events WHERE venture_id=?'
            f" AND status='attached' AND reaction IN ({holes})",
            *INTERESSE,
        ),
        'points': points,
        'depense_eur': depense,
        'points_par_euro': points_par_euro(points, depense),
        'paid': float(paid or 0),
    }
