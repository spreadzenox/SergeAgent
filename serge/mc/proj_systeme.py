#!/usr/bin/env python3
"""Projecteurs P1 Système : la population, les messages non rattachés et
l'essai total (les îlots sont dans ``proj_ilots.py``)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


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


def _fil(conn: sqlite3.Connection, contact_id: str) -> list[dict[str, Any]]:
    """Le fil d'un contact : chaque envoi (statut, raison d'un refus) et
    chaque message reçu (réaction), du plus récent au plus ancien."""
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
            (contact_id,),
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
            (contact_id,),
        ).fetchall()
    ]
    return sorted(fil, key=lambda e: e['heure'], reverse=True)[:30]


def _essai_total(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Le dernier essai total : où il en est, ses tâches dans l'ordre, les
    tickets qui attendent une réponse, et le fil de son contact. ``None``
    avant le premier essai.

    Un essai porte le numéro de la tâche qui l'a lancé
    (``tasks.trial_run``) ; celui qui tourne est noté dans
    ``runtime_flags``.
    """
    from serge.mc.proj_taches import ETATS_TACHE
    from serge.trial import active_run

    en_cours = active_run(conn)
    row = conn.execute(
        'SELECT id, created_at FROM tasks WHERE trial_run=id'
        ' ORDER BY (id=?) DESC, created_at DESC, rowid DESC LIMIT 1',
        (en_cours,),
    ).fetchone()
    if row is None:
        return None
    run = str(row[0])
    depart = conn.execute(
        "SELECT value FROM task_params WHERE task_id=? AND name='depart'",
        (run,),
    ).fetchone()
    business = conn.execute(
        'SELECT v.id, v.name, v.lifecycle FROM ventures v WHERE v.id IN'
        ' (SELECT p.value FROM task_params p JOIN tasks t ON t.id=p.task_id'
        " WHERE t.trial_run=? AND p.name='venture_id') LIMIT 1",
        (run,),
    ).fetchone()
    taches = [
        {
            'id': str(ident),
            'titre': str(titre or invocation),
            'statut': str(statut),
            'etat': ETATS_TACHE.get(str(statut), str(statut)),
            'heure': str(fini or cree),
            'erreur': str(erreur or ''),
        }
        for ident, titre, invocation, statut, cree, fini, erreur in conn.execute(
            'SELECT t.id, i.title, t.invocation_id, t.status, t.created_at,'
            ' t.finished_at, t.last_error FROM tasks t LEFT JOIN invocations i'
            ' ON i.id=t.invocation_id WHERE t.trial_run=?'
            ' ORDER BY t.created_at DESC, t.rowid DESC LIMIT 60',
            (run,),
        ).fetchall()
    ]
    contact = (
        conn.execute(
            'SELECT id, display, funnel_state FROM contacts WHERE venture_id=?'
            ' ORDER BY created_at, rowid LIMIT 1',
            (business[0],),
        ).fetchone()
        if business
        else None
    )
    return {
        'en_cours': run == en_cours,
        'lance': str(row[1]),
        'depart': str(depart[0] if depart and depart[0] else '1'),
        'business': (
            {
                'id': str(business[0]),
                'nom': str(business[1]),
                'statut': str(business[2]),
            }
            if business
            else None
        ),
        'taches': taches,
        'tickets': [
            {'id': str(r[0]), 'titre': str(r[1])}
            for r in conn.execute(
                'SELECT id, title FROM tickets WHERE trial=1'
                " AND state IN ('OPEN', 'DISCUSSING')"
                ' ORDER BY created_at DESC LIMIT 10'
            ).fetchall()
        ],
        'contact': str(contact[1]) if contact else '',
        'etape': str(contact[2]) if contact else '',
        'fil': _fil(conn, str(contact[0])) if contact else [],
    }


def project_essais(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Le bouton de l'essai total, et le dernier essai (décision Q99).

    Returns:
        Dict {boutons: les boutons sans étape qui lancent un essai,
        essai: où en est le dernier essai (ou None)}.
    """
    _ = (policy, now)
    return {
        'boutons': _boutons_sans_etape(conn, essai=True),
        'essai': _essai_total(conn),
    }


def _boutons_sans_etape(
    conn: sqlite3.Connection, *, essai: bool
) -> list[dict[str, Any]]:
    from serge.mc.proj_ecoute import boutons_de_etape

    return [
        b
        for b in boutons_de_etape(conn, '')
        if (b['couloir'] == 'trial') == essai
    ]


def project_comptes_web(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les comptes web de Serge et leurs boutons (lot 13, Q104).

    Returns:
        Dict {comptes: un par compte, sans aucun secret (son site, son
        identifiant, son état, s'il a une session gardée, ses actions du
        jour), plafond: les actions permises par jour, boutons: les
        boutons sans étape qui ne lancent pas un essai}. Exemple de
        compte : ``{id: 'reddit', site: 'https://www.reddit.com',
        identifiant: 'serge-ia', etat: 'en service', session: True,
        actions: 12, retirable: False}``.
    """
    from serge.mc.proj_compte import ETATS
    from serge.web_accounts import actions_today

    _ = now
    return {
        'comptes': [
            {
                'id': str(ident),
                'site': str(url),
                'identifiant': str(login),
                'etat': ETATS.get(str(etat), str(etat)),
                'session': bool(garde),
                # Un compte connecté avec Google vit dans le profil du
                # vrai Chrome : pas de session en base.
                'connexion': 'connecté avec Google, dans le vrai Chrome'
                if avec
                else '',
                'actions': actions_today(conn, str(ident)),
                # Un compte qui n'est pas en service peut être retiré.
                'retirable': str(etat) != 'active',
            }
            for ident, url, login, etat, garde, avec in conn.execute(
                'SELECT id, url, login, status, session_enc, sign_in_with'
                ' FROM web_accounts ORDER BY id'
            ).fetchall()
        ],
        'plafond': int(policy['web_accounts']['max_actions_per_day']),
        'boutons': _boutons_sans_etape(conn, essai=False),
    }
