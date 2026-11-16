#!/usr/bin/env python3
"""Appliquer la réponse au ticket « Choix du principal » (décision Q16 bis).

« Valider » (ou pas de réponse sous 48 heures) applique la proposition ;
« Choisir un autre » prend le business dont on a écrit le nom ou le
numéro, parmi ceux qui attendent ; « Aucun » n'en prend pas. Le business
choisi entre en construction de son produit ; les autres tests retenus
sont mis de côté. Un nom qui ne désigne aucun business qui attend ne
change rien : le ticket est rouvert, avec la raison.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.trial import lane_clause

# Un business retenu qui attend le choix, ou mis de côté par un choix
# précédent (il redevient candidat après 60 jours).
WAITING = ('SMOKE_DONE', 'PARKED')


def _waiting(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Les business qui attendent, du couloir de la tâche : ``{id: (nom,
    statut)}``."""
    return {
        str(ident): (str(name), str(status))
        for ident, name, status in conn.execute(
            'SELECT id, name, lifecycle FROM ventures WHERE lifecycle IN'
            f' (?, ?) AND {lane_clause(conn, "ventures")}',
            WAITING,
        ).fetchall()
    }


def _named(waiting: dict[str, tuple[str, str]], text: str) -> str:
    wanted = text.strip().casefold()
    for ident, (name, _status) in waiting.items():
        if wanted in (ident.casefold(), name.strip().casefold()):
            return ident
    return ''


def apply_principal(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Appliquer le choix du principal » : ``{choice_id, acte,
    texte}``.

    Rend ``ok`` (« oui », ou « non » avec ``raison``), ``chosen`` (le
    business choisi, ou vide) et ``parked`` (les autres tests retenus, à
    mettre de côté).
    """
    choice = str(args.get('choice_id') or '')
    acte = str(args.get('acte') or '')
    row = conn.execute(
        'SELECT proposed_venture_id, status FROM principal_choices WHERE id=?',
        (choice,),
    ).fetchone()
    if row is None or str(row[1]) != 'PROPOSED':
        return {'ok': 'non', 'raison': 'ce choix n’attend plus de réponse'}
    waiting = _waiting(conn)
    if acte == 'aucun':
        chosen = ''
    elif acte == 'choisir_autre':
        chosen = _named(waiting, str(args.get('texte') or ''))
        if not chosen:
            return {
                'ok': 'non',
                'choice_id': choice,
                'raison': f'« {str(args.get("texte") or "").strip()} » ne'
                ' désigne aucun business de ce ticket : écris son nom tel'
                ' qu’il est affiché',
            }
    else:
        chosen = str(row[0] or '')
        chosen = chosen if chosen in waiting else ''
    return {
        'ok': 'oui',
        'choice_id': choice,
        'decision': acte,
        'chosen': chosen,
        'parked': [
            ident
            for ident, (_name, status) in waiting.items()
            if ident != chosen and status == 'SMOKE_DONE'
        ],
    }
