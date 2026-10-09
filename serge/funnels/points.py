#!/usr/bin/env python3
"""La grille de points : jusqu'où chaque prospect est allé, en points.

Le barème est en base, sur la page Policy (famille « Grille de points ») :
un réglage par canal et par réaction, de 0 à 10 points, nommé
``points.<canal>.<réaction>``. Exemple : ``points.email.rendez-vous`` vaut
10. Une réaction sans réglage vaut 0.

Un prospect compte une fois, pour sa meilleure réaction dans son business,
tous canaux confondus (décision Q84) : un prospect qui écrit cinq fois ne
gonfle pas le total. Les points sont recalculés avec le barème du moment :
le changer recompte tous les business de la même façon.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# La famille de réglages du barème (page Policy).
FAMILLE = 'points'


def bareme(conn: sqlite3.Connection) -> dict[tuple[str, str], float]:
    """Le barème en vigueur : ``{(canal, réaction): points}``."""
    out: dict[tuple[str, str], float] = {}
    for ident, value in conn.execute(
        'SELECT id, value_json FROM policy_settings WHERE section_id=?',
        (FAMILLE,),
    ).fetchall():
        _, canal, reaction = str(ident).split('.', 2)
        out[(canal, reaction)] = float(json.loads(value) or 0)
    return out


def _meilleures(
    conn: sqlite3.Connection, where: str, param: str
) -> dict[str, dict[str, Any]]:
    """La meilleure réaction de chaque contact, parmi ses messages reçus."""
    grille = bareme(conn)
    best: dict[str, dict[str, Any]] = {}
    for contact, canal, reaction in conn.execute(
        'SELECT contact_id, channel, reaction FROM inbound_events'
        f" WHERE {where}=? AND status='attached' AND contact_id<>''"
        " AND reaction<>'' ORDER BY received_at",
        (param,),
    ).fetchall():
        points = grille.get((str(canal), str(reaction)), 0.0)
        if contact not in best or points > best[contact]['points']:
            best[str(contact)] = {
                'points': points,
                'canal': str(canal),
                'reaction': str(reaction),
            }
    return best


def points_contact(
    conn: sqlite3.Connection, contact_id: str
) -> dict[str, Any] | None:
    """La meilleure réaction d'un contact et ses points, ou ``None`` s'il
    n'a encore rien dit.

    Exemple : ``{'points': 8.0, 'canal': 'voice', 'reaction': 'intéressé'}``.
    """
    return _meilleures(conn, 'contact_id', contact_id).get(contact_id)


def points_prospects(
    conn: sqlite3.Connection, venture_id: str
) -> dict[str, dict[str, Any]]:
    """La meilleure réaction de chaque prospect d'un business, par contact."""
    return _meilleures(conn, 'venture_id', venture_id)


def points_business(conn: sqlite3.Connection, venture_id: str) -> float:
    """Le total des points d'un business : la somme, sur ses prospects, des
    points de leur meilleure réaction."""
    total = sum(
        v['points'] for v in points_prospects(conn, venture_id).values()
    )
    return round(total, 1)


def texte_points(points: float) -> str:
    """``8.0`` → ``8``, ``0.5`` → ``0,5``."""
    return f'{points:g}'.replace('.', ',')
