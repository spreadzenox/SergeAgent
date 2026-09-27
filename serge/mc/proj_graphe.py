#!/usr/bin/env python3
"""Projecteur graphe home : étapes, invocations, orbites, liens, blocages."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.etape_fiches import fiche_etape
from serge.etapes import ETAPE_IDS, etats_etapes
from serge.mc.libelles import ORBITES, phrase_noyau, phrase_recit
from serge.mc.proj_etape import invocations_chaudes, lister_invocations
from serge.mc.proj_taches import tache_en_cours
from serge.tickets.lifecycle import OPENISH


def _count(conn: sqlite3.Connection, sql: str, args: tuple = ()) -> int:
    row = conn.execute(sql, args).fetchone()
    return int(row[0]) if row else 0


def _nom_venture(conn: sqlite3.Connection, ident: str) -> str:
    if not ident:
        return ''
    row = conn.execute(
        'SELECT name FROM ventures WHERE id=?', (ident,)
    ).fetchone()
    return str(row[0] or ident) if row else ident


def _tache_recente(conn: sqlite3.Connection) -> Any:
    """La tâche en cours, sinon la dernière finie."""
    return conn.execute(
        'SELECT t.id, t.invocation_id, t.status, i.title, i.step_id,'
        " i.prompt, COALESCE(p.value, '') FROM tasks t"
        ' LEFT JOIN invocations i ON i.id=t.invocation_id'
        " LEFT JOIN task_params p ON p.task_id=t.id AND p.name='venture_id'"
        " WHERE t.status IN ('running', 'done', 'failed')"
        " ORDER BY CASE t.status WHEN 'running' THEN 0 ELSE 1 END,"
        " COALESCE(NULLIF(t.finished_at, ''), t.started_at) DESC LIMIT 1"
    ).fetchone()


def _pensee(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """La tâche en cours (ou la dernière) : de quoi cadrer le texte."""
    row = _tache_recente(conn)
    if row is None:
        return None
    etape = str(row[4] or '')
    titre = str(row[3] or row[1])
    vid = str(row[6] or '')
    en_cours = row[2] == 'running'
    return {
        'point': str(row[1]),
        'jugement': titre,
        'etape': etape,
        'etape_titre': (fiche_etape(conn, etape) or {}).get('titre') or etape,
        'tache': titre,
        'tache_id': str(row[0]),
        'venture_id': vid,
        'venture': _nom_venture(conn, vid),
        'prompt': str(row[5] or '') if en_cours else '',
        'sortie': '' if en_cours else str(row[2]),
    }


def _flux(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Les liens entre invocations de deux étapes différentes.

    Le débit d'un lien est le nombre de fois où il a transmis un résultat.
    """
    flux = []
    for row in conn.execute(
        'SELECT l.id, a.step_id, b.step_id, l.title,'
        ' (SELECT COUNT(*) FROM link_passages p WHERE p.link_id=l.id)'
        ' FROM links l JOIN invocations a ON a.id=l.from_invocation_id'
        ' JOIN invocations b ON b.id=l.to_invocation_id'
        " WHERE l.enabled=1 AND l.deleted_at='' AND a.step_id<>b.step_id"
        ' ORDER BY l.id'
    ).fetchall():
        flux.append(
            {
                'id': str(row[0]),
                'de': str(row[1]),
                'vers': str(row[2]),
                'libelle': str(row[3] or row[0]),
                'debit': int(row[4]),
            }
        )
    return flux


def project_graphe(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Carte live : les étapes et leurs invocations, orbites, liens, blocages."""
    _ = (policy, now)
    chauds = invocations_chaudes(conn)
    etats = etats_etapes(conn)
    epine = []
    llm_nodes = []
    for key, spec in etats.items():
        if key not in ETAPE_IDS:
            continue
        fiche = fiche_etape(conn, key) or {}
        invs = lister_invocations(conn, key, chauds)
        epine.append(
            {
                'id': key,
                'titre': fiche.get('titre') or key,
                'pourquoi': fiche.get('pourquoi') or '',
                'argent': fiche.get('argent') or '',
                'objet': {'type': 'etape', 'id': key},
                'jugements': invs,
                'marche': spec['marche'],
            }
        )
        llm_nodes.extend(
            {
                'id': j['id'],
                'titre': j['titre'],
                'etape': key,
                'chaud': j['chaud'],
                'objet': {'type': 'llm', 'id': j['id']},
            }
            for j in invs
        )
    placeholders = ','.join('?' * len(OPENISH))
    urgents = _count(
        conn,
        'SELECT COUNT(*) FROM tickets WHERE state IN'
        f" ({placeholders}) AND type IN ('GUICHET','VETO_AMONT','ALERT')",
        tuple(sorted(OPENISH)),
    )
    failed = _count(conn, "SELECT COUNT(*) FROM tasks WHERE status='failed'")
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
    return {
        'epine': epine,
        'orbites': [
            {'id': key, **val, 'objet': {'type': key, 'id': key}}
            for key, val in ORBITES.items()
        ],
        'llm': llm_nodes,
        'flux': _flux(conn),
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
    running = tache_en_cours(conn)
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
