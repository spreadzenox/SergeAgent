#!/usr/bin/env python3
"""Projecteur P1 : les îlots de la page Système (purs, goldens).

Fenêtre 24 h, tâche en cours suspecte après 30 min, îlots sans source =
'inconnu'. La file des tâches est lue par ``proj_taches.py``.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_outils import avant_iso
from serge.mc.proj_taches import prochaines


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
    ready = _compte(conn, "SELECT COUNT(*) FROM tasks WHERE status='ready'")
    running = _compte(
        conn, "SELECT COUNT(*) FROM tasks WHERE status='running'"
    )
    bloques = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='ready' AND not_before>?",
        (now,),
    )
    servies = prochaines(conn, now)
    if ready - bloques > 0 and not servies:
        sante = 'degrade'  # tâches prêtes non servies : file ou étape coupée
    else:
        sante = 'ok'
    resume = f'{ready} prêtes, {running} en cours'
    resume += f', {bloques} en attente de leur heure' if bloques else ''
    return {
        'id': 'scheduler',
        'label': 'Files de tâches',
        'sante': sante,
        'activite': min(1.0, (running + ready) / 10),
        'resume': resume,
    }


def _ilot_workers(
    conn: sqlite3.Connection, now: str, depuis: str
) -> dict[str, Any]:
    par_statut = _groupes(
        conn, 'SELECT status, COUNT(*) FROM tasks GROUP BY status'
    )
    failed24 = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='failed' AND finished_at>?",
        (depuis,),
    )
    suspect = _compte(
        conn,
        "SELECT COUNT(*) FROM tasks WHERE status='running' AND started_at<?",
        (avant_iso(now, minutes=30),),
    )
    if failed24 > 0:
        sante = 'erreur'
    elif suspect > 0:
        sante = 'degrade'
    else:
        sante = 'ok'
    running = par_statut.get('running', 0)
    ready = par_statut.get('ready', 0)
    resume = f'{running} en cours, {ready} prêtes'
    resume += f', {failed24} échouées (24 h)' if failed24 else ''
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
        'activite': min(1.0, recus / 10),
        'resume': f'{recus} reçus (24 h) — pas d’envoi (writer absent)',
    }


def _ilot_email(conn: sqlite3.Connection) -> dict[str, Any]:
    par_statut = _groupes(
        conn,
        "SELECT status, COUNT(*) FROM touches WHERE channel='email'"
        ' GROUP BY status',
    )
    envoyes = par_statut.get('sent', 0) + par_statut.get('delivered', 0)
    return {
        'id': 'email',
        'label': 'Email',
        'sante': 'inconnu',
        'activite': min(1.0, envoyes / 10),
        'resume': f'{envoyes} envoyés — envoi pas encore branché (lot 8)',
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
    depuis = avant_iso(now, hours=24)
    items = [
        _ilot_scheduler(conn, now),
        _ilot_workers(conn, now, depuis),
        _ilot_guards(conn, depuis),
        _ilot_funnels(conn, depuis),
        _ilot_collect(conn),
        _ilot_listen(conn, depuis),
        _ilot_inconnu('allocator', 'Arbitre', 'Pas de source (lot 6).'),
        _ilot_sms(conn, depuis),
        _ilot_email(conn),
        _ilot_inconnu('discord', 'Discord', 'Sonde gateway au lot 12.'),
        _ilot_inconnu('voix', 'Voix', 'Ledger voix au lot 11.'),
    ]
    return {'items': items}
