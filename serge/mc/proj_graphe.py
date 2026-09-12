#!/usr/bin/env python3
"""Projecteur graphe home : nœuds métier, LLM, orbites, flux, blocages."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.libelles import (
    LLM_ETAPE,
    NOEUDS,
    ORBITES,
    phrase_noyau,
    phrase_recit,
    titre_llm,
    verbe,
)
from serge.registry import load_llm_points
from serge.tickets.lifecycle import OPENISH


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0]) if row else 0


def _llm_live(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT point FROM llm_usage ORDER BY id DESC LIMIT 12"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _dernier_io(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM events WHERE type='llm.io'"
        ' ORDER BY id DESC LIMIT 1'
    ).fetchone()
    if not row:
        return None
    import json

    try:
        data = json.loads(row[0] or '{}')
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def project_graphe(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Carte live : épine, LLM, orbites, arêtes, blocages, I/O typewriter."""
    _ = (policy, now)
    points = load_llm_points()
    live = _llm_live(conn)
    running = conn.execute(
        "SELECT kind FROM work_items WHERE status='RUNNING' LIMIT 8"
    ).fetchall()
    kinds_run = {str(r[0]) for r in running}
    llm_nodes = []
    for name, spec in points.items():
        etape = LLM_ETAPE.get(name, 'test')
        llm_nodes.append(
            {
                'id': name,
                'titre': titre_llm(name),
                'etape': etape,
                'tier': spec.get('tier', 'T1'),
                'chaud': name in live or any(name in k for k in kinds_run),
                'objet': {'type': 'llm', 'id': name},
            }
        )
    placeholders = ','.join('?' * len(OPENISH))
    urgents = _count(
        conn,
        'SELECT COUNT(*) FROM tickets WHERE state IN'
        f" ({placeholders}) AND type IN ('GUICHET','VETO_AMONT','ALERT')",
        tuple(sorted(OPENISH)),
    )
    failed = _count(conn, "SELECT COUNT(*) FROM work_items WHERE status='FAILED'")
    deny = _count(
        conn,
        "SELECT COUNT(*) FROM events WHERE type='guard'"
        " AND payload_json LIKE '%false%'",
    )
    blocages = []
    if urgents:
        blocages.append(
            {'noeud': 'conversation', 'verbe': 'attend une décision humaine'}
        )
    if failed:
        blocages.append({'noeud': 'test', 'verbe': 'une tâche a échoué'})
    if deny:
        blocages.append({'noeud': 'policy', 'verbe': 'un garde-fou a refusé'})
    flux = [
        {
            'id': 'ecoute-hypo',
            'de': 'ecoute',
            'vers': 'hypothese',
            'debit': _count(conn, 'SELECT COUNT(*) FROM listen_docs'),
            'libelle': 'docs d’écoute',
        },
        {
            'id': 'hypo-test',
            'de': 'hypothese',
            'vers': 'test',
            'debit': _count(conn, 'SELECT COUNT(*) FROM campaigns'),
            'libelle': 'campagnes',
        },
        {
            'id': 'test-qualif',
            'de': 'test',
            'vers': 'qualif',
            'debit': _count(conn, 'SELECT COUNT(*) FROM contacts'),
            'libelle': 'prospects',
        },
        {
            'id': 'qualif-conv',
            'de': 'qualif',
            'vers': 'conversation',
            'debit': _count(conn, 'SELECT COUNT(*) FROM touches'),
            'libelle': 'touches',
        },
        {
            'id': 'conv-intent',
            'de': 'conversation',
            'vers': 'intent',
            'debit': _count(conn, 'SELECT COUNT(*) FROM inbound_events'),
            'libelle': 'réponses',
        },
        {
            'id': 'intent-caisse',
            'de': 'intent',
            'vers': 'caisse',
            'debit': _count(conn, 'SELECT COUNT(*) FROM transactions'),
            'libelle': 'factures',
        },
    ]
    evts = [
        {'ts': r[0], 'kind': r[1], 'titre': verbe(str(r[1]))}
        for r in conn.execute(
            'SELECT ts, type FROM events ORDER BY id DESC LIMIT 80'
        ).fetchall()
    ]
    return {
        'epine': [
            {
                'id': key,
                **val,
                'objet': {'type': 'noeud', 'id': key},
                'cible': _cible_epine(conn, key),
            }
            for key, val in NOEUDS.items()
        ],
        'orbites': [
            {'id': key, **val, 'objet': {'type': key, 'id': key}}
            for key, val in ORBITES.items()
        ],
        'llm': llm_nodes,
        'flux': flux,
        'blocages': blocages,
        'timeline': evts,
        'io': _dernier_io(conn),
    }


def project_business(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Venture active, tests, U1–U3, phrase noyau, lignée euro."""
    _ = (policy, now)
    from serge.funnels.metrics import campaign_metrics

    row = conn.execute(
        "SELECT id, name, lifecycle FROM ventures WHERE lifecycle IN"
        " ('SMOKE_RUNNING','FULL_RUNNING','SCALE','SMOKE_READY','CANDIDATE')"
        ' ORDER BY updated_at DESC LIMIT 1'
    ).fetchone()
    if row is None:
        row = conn.execute(
            'SELECT id, name, lifecycle FROM ventures ORDER BY updated_at DESC LIMIT 1'
        ).fetchone()
    venture = None
    tests = []
    u1 = u2 = u3 = 0
    paid = 0.0
    if row:
        venture = {'id': row[0], 'nom': row[1] or row[0], 'lifecycle': row[2]}
        for camp in conn.execute(
            'SELECT id, family, channel, state FROM campaigns WHERE venture_id=?',
            (row[0],),
        ).fetchall():
            m = campaign_metrics(conn, str(camp[0]))
            tests.append(
                {
                    'id': camp[0],
                    'famille': camp[1],
                    'canal': camp[2],
                    'etat': camp[3],
                    'u1': int(m.get('u1', 0)),
                    'u2': int(m.get('u2', 0)),
                    'u3': int(m.get('u3', 0)),
                }
            )
            u1 += int(m.get('u1', 0))
            u2 += int(m.get('u2', 0))
            u3 += int(m.get('u3', 0))
        paid_row = conn.execute(
            "SELECT COALESCE(SUM(amount_eur),0) FROM transactions"
            " WHERE venture_id=? AND status='paid'",
            (row[0],),
        ).fetchone()
        paid = float(paid_row[0] if paid_row else 0)
    recit = ''
    if venture:
        recit = phrase_recit(
            str(venture['nom']),
            str(venture['lifecycle']),
            u1,
            u2,
            u3,
            paid,
        )
    run = conn.execute(
        'SELECT id, kind, venture_id, created_at FROM work_items'
        " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    running = None
    if run:
        running = {
            'id': run[0],
            'kind': run[1],
            'venture_id': run[2],
            'since': run[3],
        }
    urgents = _count(
        conn,
        "SELECT COUNT(*) FROM tickets WHERE state IN ('OPEN','DRAFT')"
        " AND type IN ('GUICHET','VETO_AMONT','ALERT')",
    )
    lignage = _lignage_euro(conn)
    return {
        'venture': venture,
        'tests': tests,
        'u1': u1,
        'u2': u2,
        'u3': u3,
        'paid_eur': paid,
        'voix': phrase_noyau(urgents, running, paid),
        'recit': recit,
        'running': running,
        'lignage': lignage,
    }


def _premier(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> str:
    row = conn.execute(sql, args).fetchone()
    return str(row[0]) if row and row[0] else ''


def _cible_epine(conn: sqlite3.Connection, noeud: str) -> dict[str, str] | None:
    if noeud == 'ecoute':
        return {'type': 'ecoute', 'id': 'pages'}
    mapping = {
        'hypothese': (
            'ticket',
            "SELECT id FROM tickets WHERE type='HYPOTHESIS' ORDER BY updated_at DESC LIMIT 1",
        ),
        'test': (
            'campagne',
            'SELECT id FROM campaigns ORDER BY updated_at DESC LIMIT 1',
        ),
        'qualif': (
            'prospect',
            "SELECT id FROM contacts WHERE funnel_state != 'CUSTOMER' ORDER BY updated_at DESC LIMIT 1",
        ),
        'conversation': (
            'inbound_event',
            'SELECT id FROM inbound_events ORDER BY received_at DESC LIMIT 1',
        ),
        'intent': (
            'prospect',
            "SELECT id FROM contacts WHERE funnel_state IN ('INTENT','MEETING') LIMIT 1",
        ),
        'caisse': (
            'facture',
            "SELECT id FROM transactions WHERE status='paid' ORDER BY updated_at DESC LIMIT 1",
        ),
    }
    spec = mapping.get(noeud)
    if not spec:
        return None
    ident = _premier(conn, spec[1])
    if not ident:
        return None
    return {'type': spec[0], 'id': ident}


def _lignage_euro(conn: sqlite3.Connection) -> list[dict[str, str]]:
    tx = conn.execute(
        "SELECT id, venture_id, intent_id FROM transactions"
        " WHERE status='paid' ORDER BY updated_at DESC LIMIT 1"
    ).fetchone()
    if not tx:
        return []
    chain = [{'type': 'facture', 'id': str(tx[0])}]
    if tx[1]:
        chain.insert(0, {'type': 'venture', 'id': str(tx[1])})
    camp = conn.execute(
        'SELECT id FROM campaigns WHERE venture_id=? LIMIT 1', (tx[1],)
    ).fetchone()
    if camp:
        chain.insert(-1, {'type': 'campagne', 'id': str(camp[0])})
        touch = conn.execute(
            'SELECT id, contact_id FROM touches WHERE campaign_id=? LIMIT 1',
            (camp[0],),
        ).fetchone()
        if touch:
            chain.insert(-1, {'type': 'touch', 'id': str(touch[0])})
            if touch[1]:
                etat = conn.execute(
                    'SELECT funnel_state FROM contacts WHERE id=?',
                    (touch[1],),
                ).fetchone()
                typ = (
                    'client'
                    if etat and etat[0] == 'CUSTOMER'
                    else 'prospect'
                )
                chain.insert(-1, {'type': typ, 'id': str(touch[1])})
    return chain
