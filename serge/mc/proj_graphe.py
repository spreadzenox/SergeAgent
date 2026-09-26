#!/usr/bin/env python3
"""Projecteur graphe home : nœuds métier, LLM, orbites, flux, blocages."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.etape_fiches import compter_debit, fiche_etape
from serge.etapes import ETAPE_IDS, etats_etapes
from serge.mc.libelles import (
    ORBITES,
    phrase_noyau,
    phrase_recit,
    titre_llm,
    verbe,
)
from serge.mc.proj_etape import ORDRE, RESTE, lister_jugements
from serge.tickets.lifecycle import OPENISH


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0]) if row else 0


def _llm_live(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        'SELECT DISTINCT point FROM llm_usage ORDER BY id DESC LIMIT 12'
    ).fetchall()
    return {str(r[0]) for r in rows}


def _nom_venture(conn: sqlite3.Connection, ident: str) -> str:
    if not ident:
        return ''
    row = conn.execute(
        'SELECT name FROM ventures WHERE id=?', (ident,)
    ).fetchone()
    return str(row[0] or ident) if row else ident


def _pensee(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Dernière invocation + tâche RUNNING : de quoi cadrer le texte."""
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
        etape_row = conn.execute(
            'SELECT etape_id FROM llm_points WHERE id=?', (point,)
        ).fetchone()
        etape = str(etape_row[0] or '') if etape_row else ''
        spec = fiche_etape(conn, etape) or {}
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
    live = _llm_live(conn)
    running = conn.execute(
        "SELECT kind FROM work_items WHERE status='RUNNING' LIMIT 8"
    ).fetchall()
    kinds_run = {str(r[0]) for r in running}
    chauds = live | kinds_run
    llm_nodes = []
    rows = conn.execute(
        'SELECT id, etape_id, titre, tier FROM llm_points'
    ).fetchall()
    positions: dict[tuple[str, str], tuple[int, int, int, str]] = {}
    step_rows = conn.execute(
        'SELECT id, rang FROM pipeline_steps ORDER BY rang, id'
    ).fetchall()
    for step_rank, step in enumerate(step_rows):
        step_id = str(step[0])
        ordered = ORDRE.get(step_id, [])
        unordered = RESTE.get(step_id, [])
        for point_rank, point_id in enumerate(ordered, 1):
            positions[(step_id, point_id)] = (
                step_rank,
                0,
                point_rank,
                point_id,
            )
        for point_rank, point_id in enumerate(unordered, 1):
            positions[(step_id, point_id)] = (
                step_rank,
                1,
                point_rank,
                point_id,
            )
    rows = sorted(
        rows,
        key=lambda row: positions.get(
            (str(row[1]), str(row[0])),
            (999, 2, 999, str(row[0])),
        ),
    )
    for row in rows:
        name = str(row[0])
        llm_nodes.append(
            {
                'id': name,
                'titre': str(row[2] or '') or titre_llm(name),
                'etape': str(row[1] or '') or 'prospection_light',
                'tier': str(row[3] or '') or 'T1',
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
    failed = _count(
        conn, "SELECT COUNT(*) FROM work_items WHERE status='FAILED'"
    )
    deny = _count(
        conn,
        "SELECT COUNT(*) FROM events WHERE type='guard'"
        " AND payload_json LIKE '%false%'",
    )
    blocages = []
    if urgents:
        blocages.append(
            {
                'noeud': 'prospection_lourde',
                'verbe': 'attend une décision humaine',
            }
        )
    if failed:
        blocages.append(
            {'noeud': 'prospection_light', 'verbe': 'une tâche a échoué'}
        )
    if deny:
        blocages.append({'noeud': 'policy', 'verbe': 'un garde-fou a refusé'})
    flux = []
    for row in conn.execute(
        'SELECT id, de, vers, libelle, debit FROM etape_liens'
        ' ORDER BY rang, id'
    ):
        flux.append(
            {
                'id': str(row[0]),
                'de': str(row[1]),
                'vers': str(row[2]),
                'libelle': str(row[3]),
                'debit': compter_debit(conn, str(row[4])),
            }
        )
    etats = etats_etapes(conn)
    epine = []
    for key, spec in etats.items():
        if key not in ETAPE_IDS:
            continue
        fiche = fiche_etape(conn, key) or {}
        epine.append(
            {
                'id': key,
                'titre': fiche.get('titre') or key,
                'pourquoi': fiche.get('pourquoi') or '',
                'argent': fiche.get('argent') or '',
                'objet': {'type': 'etape', 'id': key},
                'jugements': lister_jugements(conn, key, chauds),
                'marche': spec['marche'],
                'kinds': spec['kinds'],
            }
        )
    return {
        'epine': epine,
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
        'SELECT id, name, lifecycle FROM ventures WHERE lifecycle IN'
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
            'SELECT COALESCE(SUM(amount_eur),0) FROM transactions'
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
