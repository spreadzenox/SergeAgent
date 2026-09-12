#!/usr/bin/env python3
"""Projecteur graphe home : nœuds métier, LLM, orbites, flux, blocages."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

import json

from serge.mc.libelles import (
    LLM_ETAPE,
    NOEUDS,
    ORBITES,
    phrase_noyau,
    phrase_recit,
    titre_llm,
    verbe,
)
from serge.mc.proj_etape import ETAPES, lister_jugements
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


def _nom_venture(conn: sqlite3.Connection, ident: str) -> str:
    if not ident:
        return ''
    row = conn.execute('SELECT name FROM ventures WHERE id=?', (ident,)).fetchone()
    return str(row[0] or ident) if row else ident


def _pensee(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Dernier jugement + tâche RUNNING : de quoi cadrer le texte."""
    row = conn.execute(
        'SELECT payload_json, venture_id, actor FROM events'
        " WHERE type='llm.io' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    run = conn.execute(
        'SELECT id, kind, venture_id FROM work_items'
        " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    if row is None and run is None:
        return None
    data: dict[str, Any] = {}
    vid = ''
    if row:
        try:
            blob = json.loads(row[0] or '{}')
        except ValueError:
            blob = {}
        if isinstance(blob, dict):
            data.update(blob)
        point = str(data.get('point') or row[2] or '')
        etape = LLM_ETAPE.get(point, '')
        spec = ETAPES.get(etape) or {}
        hors = {'memoire': 'Mémoire', 'policy': 'Policy'}
        data['point'] = point
        data['jugement'] = titre_llm(point) if point else ''
        data['etape'] = etape
        data['etape_titre'] = spec.get('titre') or hors.get(etape, etape)
        vid = str(row[1] or '')
    else:
        data['point'] = ''
        data['jugement'] = ''
        data['etape'] = ''
        data['etape_titre'] = ''
    if run:
        data['tache'] = verbe(str(run[1]))
        data['tache_id'] = str(run[0])
        vid = vid or str(run[2] or '')
    else:
        data['tache'] = ''
        data['tache_id'] = ''
    data['venture_id'] = vid
    data['venture'] = _nom_venture(conn, vid)
    return data


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
    return {
        'epine': [
            {
                'id': key,
                **val,
                'objet': {'type': 'etape', 'id': key},
                'jugements': lister_jugements(key, live | kinds_run),
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
        'io': _pensee(conn),
    }


def project_business(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Venture active, tests, U1–U3, phrase noyau."""
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
    }
