#!/usr/bin/env python3
"""Projecteurs P1 : îlots + scheduler (purs, goldens).

Fenêtre 24 h, RUNNING suspect après 30 min, îlots sans source = 'inconnu'.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.scheduler import next_ready


def _avant(now_iso: str, **duree: int) -> str:
    moment = datetime.fromisoformat(now_iso)
    return (moment - timedelta(**duree)).isoformat()


def _compte(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _groupes(
    conn: sqlite3.Connection, sql: str, params: tuple = ()
) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in conn.execute(sql, params).fetchall():
        out[str(row[0])] = int(row[1])
    return out


def _ilot_scheduler(conn: sqlite3.Connection, now: str) -> dict[str, Any]:
    ready = _compte(
        conn, "SELECT COUNT(*) FROM work_items WHERE status='READY'"
    )
    running = _compte(
        conn, "SELECT COUNT(*) FROM work_items WHERE status='RUNNING'"
    )
    bloques = _compte(
        conn,
        "SELECT COUNT(*) FROM work_items WHERE status='READY'"
        ' AND blocked_until>?',
        (now,),
    )
    prochain = next_ready(conn, now)
    if ready - bloques > 0 and prochain is None:
        sante = 'erreur'  # READY non servi = ventures non schedulables (B5)
    elif ready > 0 and prochain is None:
        sante = 'degrade'  # tout bloqué (retries planifiés)
    else:
        sante = 'ok'
    resume = f'{ready} prêts, {running} en cours'
    resume += f', {bloques} bloqués' if bloques else ''
    return {
        'id': 'scheduler',
        'label': 'Ordonnanceur',
        'sante': sante,
        'activite': min(1.0, (running + ready) / 10),
        'resume': resume,
    }


def _ilot_workers(
    conn: sqlite3.Connection, now: str, depuis: str
) -> dict[str, Any]:
    par_statut = _groupes(
        conn, 'SELECT status, COUNT(*) FROM work_items GROUP BY status'
    )
    failed24 = _compte(
        conn,
        "SELECT COUNT(*) FROM work_items WHERE status='FAILED'"
        ' AND updated_at>?',
        (depuis,),
    )
    suspect = _compte(
        conn,
        "SELECT COUNT(*) FROM work_items WHERE status='RUNNING'"
        ' AND updated_at<?',
        (_avant(now, minutes=30),),
    )
    if failed24 > 0:
        sante = 'erreur'
    elif suspect > 0:
        sante = 'degrade'
    else:
        sante = 'ok'
    running = par_statut.get('RUNNING', 0)
    ready = par_statut.get('READY', 0)
    resume = f'{running} en cours, {ready} prêts'
    resume += f', {failed24} échoués (24 h)' if failed24 else ''
    return {
        'id': 'workers',
        'label': 'Exécution',
        'sante': sante,
        'activite': min(1.0, (running + ready) / 10),
        'resume': resume,
    }


def _ilot_guards(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    rows = conn.execute(
        "SELECT payload_json FROM events WHERE actor='guards' AND ts>?",
        (depuis,),
    ).fetchall()
    verdicts = 0
    refus = 0
    for row in rows:
        verdicts += 1
        try:
            payload = json.loads(row[0] or '{}')
        except ValueError:
            continue
        if isinstance(payload, dict) and not payload.get('allowed', True):
            refus += 1
    return {
        'id': 'guards',
        'label': 'Gardes',
        'sante': 'ok',
        'activite': min(1.0, verdicts / 20),
        'resume': f'{verdicts} verdicts ({refus} refus)',
    }


def _ilot_funnels(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    ventures = _compte(conn, 'SELECT COUNT(*) FROM ventures')
    touches = _compte(
        conn, 'SELECT COUNT(*) FROM touches WHERE created_at>?', (depuis,)
    )
    return {
        'id': 'funnels',
        'label': 'Entonnoirs',
        'sante': 'ok',
        'activite': min(1.0, touches / 20),
        'resume': f'{ventures} ventures, {touches} touches (24 h)',
    }


def _ilot_collect(conn: sqlite3.Connection) -> dict[str, Any]:
    par_statut = _groupes(
        conn, 'SELECT status, COUNT(*) FROM transactions GROUP BY status'
    )
    total = sum(par_statut.values())
    retards = par_statut.get('overdue', 0)
    payees = par_statut.get('paid', 0)
    resume = f'{total} intentions ({payees} payées)'
    resume += f', {retards} en retard' if retards else ''
    return {
        'id': 'collect',
        'label': 'Collecte',
        'sante': 'erreur' if retards else 'ok',
        'activite': min(1.0, total / 10),
        'resume': resume,
    }


def _ilot_listen(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    docs = _compte(
        conn,
        'SELECT COUNT(*) FROM listen_docs WHERE fetched_at>?',
        (depuis,),
    )
    return {
        'id': 'listen',
        'label': 'Écoute',
        'sante': 'ok',
        'activite': min(1.0, docs / 20),
        'resume': f'{docs} documents (24 h)',
    }


def _ilot_sms(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    envois = _compte(conn, "SELECT COUNT(*) FROM touches WHERE channel='sms'")
    recus = _compte(
        conn,
        "SELECT COUNT(*) FROM inbound_events WHERE channel='sms'"
        ' AND received_at>?',
        (depuis,),
    )
    return {
        'id': 'sms',
        'label': 'SMS',
        'sante': 'ok',
        'activite': min(1.0, (envois + recus) / 10),
        'resume': f'{envois} envois, {recus} reçus (24 h)',
    }


def _ilot_email(conn: sqlite3.Connection, depuis: str) -> dict[str, Any]:
    par_statut = _groupes(
        conn,
        "SELECT status, COUNT(*) FROM touches WHERE channel='email'"
        ' GROUP BY status',
    )
    file = _compte(
        conn,
        "SELECT COUNT(*) FROM work_items WHERE status IN ('READY','RUNNING')"
        " AND kind LIKE 'email.%'",
    )
    failed = _compte(
        conn,
        "SELECT COUNT(*) FROM work_items WHERE status='FAILED'"
        " AND kind LIKE 'email.%' AND updated_at>?",
        (depuis,),
    )
    envoyes = par_statut.get('sent', 0) + par_statut.get('delivered', 0)
    resume = f'{file} en file, {envoyes} envoyés'
    resume += f', {failed} échoués (24 h)' if failed else ''
    return {
        'id': 'email',
        'label': 'Email',
        'sante': 'erreur' if failed else 'ok',
        'activite': min(1.0, (file + envoyes) / 10),
        'resume': resume,
    }


def _ilot_inconnu(ilot_id: str, label: str, resume: str) -> dict[str, Any]:
    return {
        'id': ilot_id,
        'label': label,
        'sante': 'inconnu',
        'activite': 0.0,
        'resume': resume,
    }


def project_ilots(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """11 îlots : santé + activité + résumé FR (P1 Système).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, label, sante, activite, resume}]}.
    """
    _ = policy
    depuis = _avant(now, hours=24)
    items = [
        _ilot_scheduler(conn, now),
        _ilot_workers(conn, now, depuis),
        _ilot_guards(conn, depuis),
        _ilot_funnels(conn, depuis),
        _ilot_collect(conn),
        _ilot_listen(conn, depuis),
        _ilot_inconnu('allocator', 'Arbitre', 'Pas de source (lot 6).'),
        _ilot_sms(conn, depuis),
        _ilot_email(conn, depuis),
        _ilot_inconnu('discord', 'Discord', 'Sonde gateway au lot 12.'),
        _ilot_inconnu('voix', 'Voix', 'Ledger voix au lot 11.'),
    ]
    return {'items': items}


def project_scheduler(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Prochain READY + compteurs de file (P1 scheduler).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {next: {id, kind, venture_id} | None, ready, running, bloques}.
    """
    _ = policy
    prochain = next_ready(conn, now)
    suivant = None
    if prochain is not None:
        suivant = {
            'id': str(prochain['id']),
            'kind': str(prochain['kind']),
            'venture_id': str(prochain.get('venture_id') or ''),
        }
    return {
        'next': suivant,
        'ready': _compte(
            conn, "SELECT COUNT(*) FROM work_items WHERE status='READY'"
        ),
        'running': _compte(
            conn, "SELECT COUNT(*) FROM work_items WHERE status='RUNNING'"
        ),
        'bloques': _compte(
            conn,
            "SELECT COUNT(*) FROM work_items WHERE status='READY'"
            ' AND blocked_until>?',
            (now,),
        ),
    }
