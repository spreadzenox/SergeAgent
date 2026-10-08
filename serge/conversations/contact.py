#!/usr/bin/env python3
"""Trouver un contact, et noter une adresse qu'il donne.

Deux capacités, d'abord pour l'agent vocal : un appelant inconnu dit son
nom ou son e-mail, l'agent cherche sa fiche ; une personne qui veut
recevoir un document donne son e-mail, l'agent le note sur sa fiche
(décision Q83).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.store import append_event
from serge.funnels.contact_errors import ContactError
from serge.funnels.contacts import add_address, normalise_value

# Les fiches rendues au plus par une recherche.
SEARCH_MAX = 5
_EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')


def contact_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Chercher un contact » : ``{query}``.

    Cherche par e-mail ou numéro exacts, sinon par un morceau du nom (une
    fiche peut porter l'entreprise : « Marc (Acme) »). Rend au plus 5
    fiches : numéro, nom, business, étape. Jamais ses adresses ni son fil :
    une personne reconnue seulement par son nom n'entend aucune information
    sensible.
    """
    query = str(args.get('query') or '').strip()
    if len(query) < 3:
        return {'ok': False, 'code': 'recherche_trop_courte', 'rows': []}
    found = conn.execute(
        "SELECT DISTINCT c.id, c.display, COALESCE(v.name, ''),"
        ' c.funnel_state FROM contacts c'
        ' LEFT JOIN ventures v ON v.id=c.venture_id'
        ' LEFT JOIN contact_addresses a ON a.contact_id=c.id'
        " WHERE (a.channel='email' AND a.value_norm=?)"
        " OR (a.channel='phone' AND a.value_norm=?)"
        ' OR c.display LIKE ? ORDER BY c.created_at DESC LIMIT ?',
        (
            normalise_value('email', query),
            normalise_value('phone', query) or '-',
            f'%{query}%',
            SEARCH_MAX,
        ),
    ).fetchall()
    rows = [
        {
            'id': str(r[0]),
            'name': str(r[1]),
            'business': str(r[2]),
            'stage': str(r[3]),
        }
        for r in found
    ]
    return {'ok': True, 'rows': rows}


def add_contact_address(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Noter une adresse » : ``{contact_id, channel, value}``.

    Ajoute l'adresse à la fiche, à côté des autres (une adresse n'est
    jamais écrasée). Exemple : ``email``, ``marc@acme.fr``.
    """
    contact = str(args.get('contact_id') or '')
    channel = str(args.get('channel') or '')
    value = str(args.get('value') or '').strip()
    if channel not in ('email', 'phone'):
        return {'ok': False, 'code': 'sorte_d_adresse_inconnue'}
    if channel == 'email' and not _EMAIL.fullmatch(value):
        return {'ok': False, 'code': 'adresse_e-mail_invalide'}
    try:
        added = add_address(conn, contact, channel, value)
    except ContactError as exc:
        return {'ok': False, 'code': str(exc)}
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='contact.address_added',
        payload={'channel': channel, 'added': added},
        rows=[('contacts', contact)],
    )
    return {'ok': True, 'added': added}
