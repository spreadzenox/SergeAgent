#!/usr/bin/env python3
"""Projecteurs P0 Live : urgents, feed, jauges (la file : proj_taches.py).

Le feed est la liste « Activité » de la page En direct : les faits du
journal, les tickets, les envois et les messages reçus, du plus récent au
plus ancien. Un fait de tâche dit de quelle tâche il parle, les détails
d'une tâche restent sur sa fiche, et les tâches de routine pareilles font
une seule ligne.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.contacts import address_value
from serge.llm.runtime import llm_spend
from serge.mc.libelles import EVENTS
from serge.mc.proj_historique import routine
from serge.mc.proj_outils import apres_iso, charge_json
from serge.tickets.lifecycle import OPENISH


def project_urgents(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Tickets urgents : un guichet qui expire dans le quart d'heure (P0
    urgents).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, type, titre, expiry_at}]} (cap 20, expiries first).
    """
    _ = policy
    placeholders = ','.join('?' * len(OPENISH))
    rows = conn.execute(
        'SELECT id, type, title, expiry_at FROM tickets WHERE state IN'
        f" ({placeholders}) AND type='GUICHET' AND expiry_at<>''"
        ' AND expiry_at<? ORDER BY expiry_at LIMIT 20',
        (*sorted(OPENISH), apres_iso(now, minutes=15)),
    ).fetchall()
    return {
        'items': [
            {
                'id': row[0],
                'type': row[1],
                'titre': row[2],
                'expiry_at': row[3],
            }
            for row in rows
        ]
    }


# Ce qu'une tâche fait pendant qu'elle tourne (ses appels d'outils, ses
# commandes, ses lignes écrites) se lit sur sa fiche, pas dans l'activité :
# une seule tâche du navigateur y mettrait trente lignes.
DETAILS_DE_TACHE = frozenset(
    (
        'tool.call',
        'sandbox.command',
        'write.inserted',
        'write.updated',
        'write.skipped',
    )
)
# Combien de faits on relit pour remplir l'activité, une fois ces détails
# écartés.
FAITS_LUS = 400
LIGNES = 30
# Ce qu'un fait dit de lui-même en court : son erreur, la raison d'un
# refus, l'expéditeur d'un SMS.
PRECISIONS = ('error', 'reason', 'raison', 'de')


def _taches(conn: sqlite3.Connection, ids: set[str]) -> dict[str, Any]:
    """De chaque tâche : le titre de son invocation, et si c'est une tâche
    de routine (voir ``proj_historique.routine``)."""
    if not ids:
        return {}
    return {
        str(ident): (str(titre), routine(str(origine), a_rendu))
        for ident, titre, origine, a_rendu in conn.execute(
            "SELECT t.id, COALESCE(NULLIF(i.title, ''), t.invocation_id),"
            " t.origin, t.answer_json<>'' FROM tasks t"
            ' LEFT JOIN invocations i ON i.id=t.invocation_id'
            f' WHERE t.id IN ({",".join("?" * len(ids))})',
            sorted(ids),
        )
    }


def _feed_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Les faits du journal, chacun avec de quoi le reconnaître : le titre
    de l'invocation pour un fait de tâche (« Tâche terminée — Fouiller un
    réseau »), le bouton cliqué, l'erreur d'un échec."""
    faits = []
    for row in conn.execute(
        'SELECT id, ts, type, payload_json FROM events'
        ' ORDER BY id DESC LIMIT ?',
        (FAITS_LUS,),
    ).fetchall():
        extra = charge_json(row[3])
        if row[2] in DETAILS_DE_TACHE and extra.get('task'):
            continue
        extra['event_id'] = str(row[0])
        faits.append((str(row[1]), str(row[2]), extra))
    taches = _taches(
        conn, {str(e['task']) for _, _, e in faits if e.get('task')}
    )
    boutons = {
        str(ident): str(titre)
        for ident, titre in conn.execute(
            "SELECT id, title FROM triggers WHERE event='button'"
        )
    }
    items = []
    for ts, sorte, extra in faits:
        bouton = boutons.get(str(extra.get('trigger_id') or ''))
        titre, de_routine = taches.get(
            str(extra.get('task') or ''), ('', False)
        )
        sujet = f'bouton « {bouton} »' if bouton else titre
        precision = next(
            (str(extra[c]) for c in PRECISIONS if extra.get(c)), ''
        )
        item = {
            'ts': ts,
            'source': 'event',
            'kind': sorte,
            'titre': ' : '.join(filter(None, (sujet, precision))),
            'extra': extra,
        }
        if sorte in EVENTS:
            item['libelle'] = EVENTS[sorte]
        if de_routine and sorte.startswith('task.'):
            item['routine'] = True
        items.append(item)
    return items


def _regroupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Les tâches de routine pareilles font une seule ligne : une relève
    qui finit toutes les deux minutes ne remplit pas l'activité. La ligne
    est à la place de la plus récente, compte les autres (``n``) et dit
    depuis quand (``depuis``). Tout le reste garde sa ligne."""
    lignes: list[dict[str, Any]] = []
    ouvertes: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        if not item.pop('routine', False):
            lignes.append(item)
            continue
        cle = (str(item['kind']), str(item['titre']))
        tete = ouvertes.get(cle)
        if tete is None:
            ouvertes[cle] = item
            lignes.append(item)
        else:
            tete['n'] = tete.get('n', 1) + 1
            tete['depuis'] = item['ts']
    return lignes


def _feed_tickets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT te.ts, te.kind, te.actor, t.id, t.title'
        ' FROM ticket_events te LEFT JOIN tickets t'
        ' ON t.id=te.ticket_id ORDER BY te.id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[0],
                'source': 'ticket',
                'kind': row[1],
                'titre': str(row[4] or ''),
                'extra': {'ticket_id': row[3], 'actor': row[2]},
            }
        )
    return items


def _feed_touches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT t.id, t.created_at, t.channel, t.kind, t.status,'
        ' c.display, t.contact_id'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' ORDER BY t.created_at DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[1],
                'source': 'touche',
                'kind': f'{row[2]}.{row[4]}',
                'titre': str(
                    row[5]
                    or address_value(conn, str(row[6] or ''), 'email')
                    or address_value(conn, str(row[6] or ''), 'phone')
                    or row[6]
                    or ''
                ),
                'extra': {
                    'contact_kind': row[3],
                    'touch_id': str(row[0]),
                    'contact_id': str(row[6] or ''),
                },
            }
        )
    return items


def _feed_recus(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Les messages reçus (e-mails, appels), avec ce qu'en a dit « Traiter
    une réponse » ; un message que Serge n'a pas su rattacher le dit."""
    items = []
    for row in conn.execute(
        'SELECT i.id, i.received_at, i.channel, i.status, i.reaction,'
        ' i.address, i.contact_id, c.display'
        ' FROM inbound_events i LEFT JOIN contacts c ON c.id=i.contact_id'
        ' ORDER BY i.received_at DESC LIMIT 30'
    ).fetchall():
        qui = str(row[7] or row[5] or row[6] or '')
        if row[3] == 'unattached':
            quoi = 'pas rattaché'
        else:
            quoi = str(row[4] or '')
        items.append(
            {
                'ts': row[1],
                'source': 'reçu',
                'kind': f'{row[2]}.recu',
                'titre': f'{qui} ({quoi})' if quoi else qui,
                'extra': {
                    'inbound_id': str(row[0]),
                    'contact_id': str(row[6] or ''),
                },
            }
        )
    return items


def project_feed(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Feed unifié : événements, tickets, envois et messages reçus, triés
    (P0 feed).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{ts, source, kind, titre, extra}] cap 30} ; un fait
        du journal porte aussi ``libelle``, et une ligne qui en regroupe
        plusieurs ``n`` et ``depuis``.
    """
    _ = (policy, now)
    items = (
        _feed_events(conn)
        + _feed_tickets(conn)
        + _feed_touches(conn)
        + _feed_recus(conn)
    )
    items.sort(key=lambda item: str(item['ts']), reverse=True)
    return {'items': _regroupe(items)[:LIGNES]}


def _quota_jour(quotas: Mapping[str, Any], cle: str) -> int:
    try:
        return int(quotas.get(cle, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _touches_jour(conn: sqlite3.Connection, canal: str, jour: str) -> int:
    """Les envois partis ce jour-là, comptés comme le fait « Envoyer un
    message » pour son plafond du jour."""
    row = conn.execute(
        'SELECT COUNT(*) FROM touches WHERE channel=?'
        " AND status='sent' AND sent_at LIKE ?",
        (canal, f'{jour}%'),
    ).fetchone()
    return int(row[0] if row else 0)


def _barre(
    conn: sqlite3.Connection, canal: str, faits: int, quota: int
) -> dict[str, Any]:
    """Le compteur du jour d'un canal ; ``branche`` dit si le canal peut
    envoyer sur ce serveur (catalogue ``canaux``)."""
    row = conn.execute(
        'SELECT etat FROM canaux WHERE id=?', (canal,)
    ).fetchone()
    return {
        'faits': faits,
        'quota': quota,
        'ratio': (faits / quota) if quota > 0 else None,
        'branche': row is not None and str(row[0]) == 'branche',
    }


def project_jauges(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Budgets : le coût des modèles du jour et du mois, et les quotas
    quotidiens de la Policy.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (budget, canaux).
        now: Maintenant ISO UTC.

    Returns:
        Dict llm / mois / email / voix (ratio None si plafond 0,
        ``branche`` faux pour un canal qui ne peut pas envoyer ici).
    """
    day = now[:10]
    depense = llm_spend(conn, policy, day)
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    eur = depense.eur
    # Ce que Serge nous coûte en IA ce mois-ci (décision Q68).
    mois = llm_spend(conn, policy, day[:7]).eur
    cap_mois = float(budget.get('monthly_eur', 0) or 0)
    email = _barre(
        conn,
        'email',
        _touches_jour(conn, 'email', day),
        _quota_jour(
            (policy.get('channels') or {}).get('email') or {}, 'max_per_day'
        ),
    )
    return {
        'llm': {
            'tokens_jour': depense.tokens,
            # Coût réel donné par OpenRouter ; les jetons des appels dont le
            # coût n'est pas connu sont comptés à part, jamais estimés.
            'eur': round(eur, 4),
            'jetons_sans_cout': depense.unknown_tokens,
            'plafond_eur': cap,
            'ratio': (eur / cap) if cap > 0 else None,
            'libelle': 'Modèles, aujourd’hui',
        },
        'mois': {
            'eur': round(mois, 4),
            'plafond_eur': cap_mois,
            'ratio': (mois / cap_mois) if cap_mois > 0 else None,
            'libelle': 'Ce que Serge coûte ce mois-ci',
        },
        'email': {
            **email,
            'envoyes': email['faits'],
            'libelle': 'E-mails',
        },
        'voix': {
            **_barre(
                conn,
                'voice',
                _touches_jour(conn, 'voice', day),
                _quota_jour(
                    (policy.get('channels') or {}).get('voice') or {},
                    'max_per_day',
                ),
            ),
            'libelle': 'Appels',
        },
    }
