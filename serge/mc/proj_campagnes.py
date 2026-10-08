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


def project_non_rattaches(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les messages reçus d'inconnus, que Serge ne traite pas (Q37, Q79).

    Un message qui ne répond à aucun envoi de Serge et vient d'une adresse
    inconnue reste ici : Julien ou Clem décident quoi en faire.

    Returns:
        Dict {items: [{heure, canal, expediteur, objet, extrait}]}, les 30
        plus récents.
    """
    _ = (policy, now)
    return {
        'items': [
            {
                'heure': str(recu),
                'canal': str(canal),
                'expediteur': str(adresse),
                'objet': str(objet),
                'extrait': str(texte)[:200],
            }
            for recu, canal, adresse, objet, texte in conn.execute(
                'SELECT received_at, channel, address, subject, body'
                " FROM inbound_events WHERE status='unattached'"
                ' ORDER BY received_at DESC LIMIT 30'
            ).fetchall()
        ]
    }


def _dernier_essai(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Le fil du dernier contact d'essai : chaque envoi (statut, raison
    d'un refus) et chaque message reçu (réaction), du plus récent au plus
    ancien. ``None`` avant le premier essai."""
    row = conn.execute(
        'SELECT c.id, c.display, c.funnel_state FROM contacts c'
        " JOIN ventures v ON v.id=c.venture_id WHERE v.lifecycle='TEST'"
        ' ORDER BY c.created_at DESC, c.rowid DESC LIMIT 1'
    ).fetchone()
    if row is None:
        return None
    fil = [
        {
            'heure': str(quand),
            'sens': 'envoi',
            'canal': str(canal),
            'sorte': str(sorte),
            'statut': str(statut),
            'detail': str(erreur or objet or ''),
        }
        for quand, canal, sorte, statut, erreur, objet in conn.execute(
            "SELECT COALESCE(NULLIF(sent_at, ''), updated_at), channel, kind,"
            ' status, last_error, subject FROM touches WHERE contact_id=?',
            (row[0],),
        ).fetchall()
    ] + [
        {
            'heure': str(quand),
            'sens': 'reçu',
            'canal': str(canal),
            'sorte': str(reaction or 'pas encore lu'),
            'statut': str(statut),
            'detail': str(texte or '')[:120],
        }
        for quand, canal, reaction, statut, texte in conn.execute(
            'SELECT received_at, channel, reaction, status, body'
            ' FROM inbound_events WHERE contact_id=?',
            (row[0],),
        ).fetchall()
    ]
    return {
        'contact': str(row[1]),
        'etape': str(row[2]),
        'fil': sorted(fil, key=lambda e: e['heure'], reverse=True)[:30],
    }


def project_essais(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les boutons sans étape (« Lancer un essai ») et l'état des canaux.

    Returns:
        Dict {boutons: [...] (comme la page Écoute), essai: le fil du
        dernier contact d'essai (ou None), canaux: [{id, titre, etat,
        releve}]} : un canal « branche » ou « prevu », et sa dernière
        relève.
    """
    from serge.mc.proj_ecoute import boutons_de_etape

    _ = (policy, now)
    return {
        'boutons': boutons_de_etape(conn, ''),
        'essai': _dernier_essai(conn),
        'canaux': [
            {
                'id': str(ident),
                'titre': str(titre),
                'etat': str(etat),
                'releve': str(releve or ''),
            }
            for ident, titre, etat, releve in conn.execute(
                'SELECT id, titre, etat, polled_at FROM canaux ORDER BY id'
            ).fetchall()
        ],
    }
