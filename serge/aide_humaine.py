#!/usr/bin/env python3
"""Appeler un humain quand une page le demande (un captcha), en deux temps.

1. **Êtes-vous prêts ?** La tâche s'arrête (elle ne dort pas en tenant un
   navigateur ouvert) et un ticket ``GUICHET_PRET`` le demande aux
   administrateurs, avec une mention sur Discord. « Je suis prêt » la fait
   repartir du début ; « Abandonner » aussi, et l'outil lui répond alors
   qu'elle doit faire sans.
2. **À toi.** Repartie, la tâche refait son parcours ; au même blocage,
   elle rappelle l'outil. Un ticket ``GUICHET`` envoie le lien de l'écran
   du vrai Chrome (``/owner/vrai-chrome`` dans Mission Control, derrière
   sa connexion), l'onglet de la tâche passe devant, et l'outil attend
   « C'est fait » (10 minutes par défaut, page Policy, « Bac à sable »).
   Sans réponse, le ticket est annulé et on revient au premier temps.

Exemple : le paiement test arrive au captcha de Stripe, s'arrête ; Clem
clique « Je suis prêt » ; deux minutes après, il reçoit le lien, coche le
captcha dans l'écran, clique « C'est fait » ; le paiement continue.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from serge.coupe_circuit import heartbeat_marche
from serge.db.store import append_event
from serge.ingress.caddy import public_hostname
from serge.policy_store import policy_en_vigueur
from serge.sandbox.sessions import montrer
from serge.tickets.lifecycle import cancel, create_ticket, publish
from serge.tickets.types import ticket_types

PRET = 'GUICHET_PRET'
ECRAN = 'GUICHET'
ADRESSE_ECRAN = '/owner/vrai-chrome'
# Tous les combien l'outil regarde si l'humain a répondu.
PAUSE_S = 5.0
TITRE_MAX = 80


def human_help(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any]:
    """L'outil « Appeler un humain » : le premier ou le second temps,
    d'après le dernier ticket d'aide de la tâche et ses réponses."""
    task_id = str(args.get('task_id') or '')
    raison = str(args.get('raison') or '').strip() or 'une page bloque'
    if not task_id:
        return {'ok': False, 'code': 'sans_tache'}
    dernier = conn.execute(
        'SELECT id, type FROM tickets WHERE ref_id=? AND type IN (?, ?)'
        ' ORDER BY created_at DESC, rowid DESC LIMIT 1',
        (task_id, PRET, ECRAN),
    ).fetchone()
    reponses = _reponses(conn, str(dernier[0])) if dernier else {}
    if dernier and 'abandonner' in reponses:
        return _sans_humain()
    if dernier and dernier[1] == PRET:
        if 'pret' in reponses:
            return _a_l_ecran(conn, task_id, raison, invocation_id)
        return {
            'ok': True,
            'gel': True,
            'ticket_id': str(dernier[0]),
            'detail': 'la tâche attend qu’un humain soit prêt',
        }
    attente = _attente_min(conn)
    fini = reponses.get('cest_fait', '')
    if fini and fini >= _il_y_a(attente):
        # L'humain vient de finir : il est encore là.
        return _a_l_ecran(conn, task_id, raison, invocation_id)
    return _demander(conn, task_id, raison, invocation_id)


def _reponses(conn: sqlite3.Connection, ticket_id: str) -> dict[str, str]:
    """Les boutons cliqués sur un ticket, avec l'heure de la réponse."""
    return {
        str(acte): str(quand)
        for acte, quand in conn.execute(
            'SELECT acte, created_at FROM ticket_answers WHERE ticket_id=?'
            ' ORDER BY created_at',
            (ticket_id,),
        )
    }


def _attente_min(conn: sqlite3.Connection) -> int:
    reglages = policy_en_vigueur(conn)['sandbox']['vrai_chrome']
    return int(reglages['attente_minutes'])


def _il_y_a(minutes: int) -> str:
    return (datetime.now(UTC) - timedelta(minutes=minutes)).isoformat()


def _sans_humain() -> dict[str, Any]:
    return {
        'ok': False,
        'code': 'sans_humain',
        'detail': 'personne n’est disponible : continue sans, et dis dans'
        ' ta réponse ce qui a bloqué',
    }


def _ticket(
    conn: sqlite3.Connection,
    kind: str,
    titre: str,
    payload: dict[str, str],
    *,
    ttl_minutes: int | None = None,
) -> str:
    return create_ticket(
        conn,
        ticket_types(conn),
        kind,
        titre[:TITRE_MAX],
        payload,
        creator='serge',
        ttl_minutes=ttl_minutes,
    )


def _noter(
    conn: sqlite3.Connection, invocation_id: str, task_id: str, etape: str
) -> None:
    append_event(
        conn,
        actor=f'invocation:{invocation_id}',
        type='human.help',
        payload={'task': task_id, 'etape': etape},
    )


def _demander(
    conn: sqlite3.Connection, task_id: str, raison: str, invocation_id: str
) -> dict[str, Any]:
    """Premier temps : « êtes-vous prêts ? », et la tâche s'arrête."""
    ticket_id = _ticket(
        conn,
        PRET,
        f'Un humain, prêt ? {raison}',
        {
            'en_bref': raison,
            'action_requise': (
                'Clique « Je suis prêt » quand tu as quelques minutes : la'
                ' tâche repart du début, et un second ticket t’envoie le lien'
                ' de l’écran du navigateur dès qu’elle arrive au blocage.'
            ),
            'point_llm': invocation_id,
        },
    )
    # La réponse fera repartir la tâche (serge/tickets/reponses.py).
    conn.execute(
        "UPDATE tickets SET ref_table='tasks', ref_id=? WHERE id=?",
        (task_id, ticket_id),
    )
    publish(conn, ticket_id)
    _noter(conn, invocation_id, task_id, 'pret')
    return {
        'ok': True,
        'gel': True,
        'ticket_id': ticket_id,
        'detail': 'la tâche s’arrête et attend qu’un humain soit prêt',
    }


def _a_l_ecran(
    conn: sqlite3.Connection, task_id: str, raison: str, invocation_id: str
) -> dict[str, Any]:
    """Second temps : le lien de l'écran, puis l'attente de « C'est fait »."""
    if not montrer(task_id):
        return {
            'ok': False,
            'code': 'pas_d_ecran',
            'detail': 'aucun onglet du vrai Chrome pour cette tâche : ouvre'
            ' la page bloquée avec les outils du vrai Chrome, puis rappelle'
            ' cet outil',
        }
    attente = _attente_min(conn)
    hote = public_hostname()
    lien = f'https://{hote}{ADRESSE_ECRAN}' if hote else ADRESSE_ECRAN
    ticket_id = _ticket(
        conn,
        ECRAN,
        f'À toi : {raison}',
        {
            'contexte': raison,
            'action_requise': (
                'Ouvre l’écran (connecte-toi à Mission Control si besoin),'
                ' fais ce qui bloque, puis clique « C’est fait ». La tâche'
                f' attend {attente} minutes.'
            ),
            'lien_stream': lien,
        },
        ttl_minutes=attente + 1,
    )
    conn.execute(
        'UPDATE tickets SET ref_id=? WHERE id=?', (task_id, ticket_id)
    )
    publish(conn, ticket_id)
    _noter(conn, invocation_id, task_id, 'ecran')
    # Le ticket part, et la base reste libre pour la réponse de l'humain.
    conn.commit()
    fin = time.monotonic() + attente * 60
    while time.monotonic() < fin:
        reponses = _reponses(conn, ticket_id)
        if 'cest_fait' in reponses:
            _noter(conn, invocation_id, task_id, 'fait')
            return {
                'ok': True,
                'detail': 'l’humain a fini : relis la page ou prends une'
                ' capture, puis continue',
            }
        if 'abandonner' in reponses:
            return _sans_humain()
        if not heartbeat_marche(conn):
            cancel(conn, ticket_id, 'Serge arrêté')
            return {'ok': False, 'code': 'serge_arrete'}
        time.sleep(PAUSE_S)
    cancel(conn, ticket_id, 'personne n’a répondu à temps')
    _noter(conn, invocation_id, task_id, 'sans_reponse')
    return _demander(conn, task_id, raison, invocation_id)
