#!/usr/bin/env python3
"""Projecteurs P1 : campagnes, population, email (purs, goldens).

Style inline (4 GROUP BY — les helpers _compte/_groupes vivent dans
proj_ilots, justifiés par ses 11 îlots).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


def project_campagnes(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Campagnes + cooldowns comptes (P1 campagnes).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, family, channel, state, n_target, envoyes,
        touches}], cooldowns: [{venue, handle, jusqu_a}]}.
    """
    _ = policy
    envoyes: dict[str, int] = {}
    for row in conn.execute(
        'SELECT campaign_id, COUNT(*) FROM touches WHERE status IN'
        " ('sent','delivered') GROUP BY campaign_id"
    ).fetchall():
        envoyes[str(row[0])] = int(row[1])
    totaux: dict[str, int] = {}
    for row in conn.execute(
        'SELECT campaign_id, COUNT(*) FROM touches GROUP BY campaign_id'
    ).fetchall():
        totaux[str(row[0])] = int(row[1])
    items = []
    for row in conn.execute(
        'SELECT id, family, channel, state, n_target FROM campaigns'
        ' ORDER BY updated_at DESC'
    ).fetchall():
        cid = str(row[0])
        items.append(
            {
                'id': cid,
                'family': str(row[1]),
                'channel': str(row[2]),
                'state': str(row[3]),
                'n_target': int(row[4]),
                'envoyes': envoyes.get(cid, 0),
                'touches': totaux.get(cid, 0),
            }
        )
    cooldowns = []
    for row in conn.execute(
        'SELECT venue, handle, cooldown_until FROM accounts_standing'
        ' WHERE cooldown_until>? ORDER BY cooldown_until',
        (now,),
    ).fetchall():
        cooldowns.append(
            {
                'venue': str(row[0]),
                'handle': str(row[1]),
                'jusqu_a': str(row[2]),
            }
        )
    return {'items': items, 'cooldowns': cooldowns}


def project_population(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Contacts par état + ventures par cycle (P1, lent).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {contacts: {etat: n}, ventures: {cycle: n}}.
    """
    _ = (policy, now)
    contacts: dict[str, int] = {}
    for row in conn.execute(
        'SELECT funnel_state, COUNT(*) FROM contacts GROUP BY funnel_state'
    ).fetchall():
        contacts[str(row[0])] = int(row[1])
    ventures: dict[str, int] = {}
    for row in conn.execute(
        'SELECT lifecycle, COUNT(*) FROM ventures GROUP BY lifecycle'
    ).fetchall():
        ventures[str(row[0])] = int(row[1])
    return {'contacts': contacts, 'ventures': ventures}


def project_email(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Volumes email + dernière activité (P1 workers email).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {par_statut: {statut: n}, derniere_activite: ISO ou ''}.
    """
    _ = (policy, now)
    par_statut: dict[str, int] = {}
    for row in conn.execute(
        "SELECT status, COUNT(*) FROM touches WHERE channel='email'"
        ' GROUP BY status'
    ).fetchall():
        par_statut[str(row[0])] = int(row[1])
    row = conn.execute(
        "SELECT MAX(updated_at) FROM touches WHERE channel='email'"
    ).fetchone()
    derniere = str(row[0] or '') if row else ''
    return {'par_statut': par_statut, 'derniere_activite': derniere}
