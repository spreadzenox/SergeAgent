#!/usr/bin/env python3
"""Projecteurs P4 Mémoire : 5 couches (C1-C5), consolidation, requested (purs)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_outils import charge_json
from serge.memory.consolidate import due_for_consolidation, last_run
from serge.memory.summaries import get_summary
from serge.points.interact import strip_ids


def project_couches(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Synthèse des 5 couches de mémoire de Serge (P4 Mémoire).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {c1, c2, c3, c4, c5} avec compteurs et listes d'items.
    """
    _ = (policy, now)
    # C1 : Épisodes & archives
    arc_rows = conn.execute(
        'SELECT id, path, period, count, sha256, created_at'
        ' FROM episode_archives ORDER BY id DESC LIMIT 10'
    ).fetchall()
    tot_arc = conn.execute(
        'SELECT COUNT(*), COALESCE(SUM(count), 0) FROM episode_archives'
    ).fetchone()
    c1 = {
        'total_archives': int(tot_arc[0]) if tot_arc else 0,
        'total_episodes': int(tot_arc[1]) if tot_arc else 0,
        'archives': [
            {
                'id': row[0],
                'path': str(row[1]),
                'period': str(row[2]),
                'count': int(row[3]),
                'sha256': str(row[4])[:12],
                'created_at': str(row[5]),
            }
            for row in arc_rows
        ],
    }

    # C2 : Playbooks
    pb_rows = conn.execute(
        'SELECT id, name, conditions, steps_json, scope, updated_at'
        ' FROM playbooks ORDER BY updated_at DESC LIMIT 20'
    ).fetchall()
    tot_pb = conn.execute('SELECT COUNT(*) FROM playbooks').fetchone()[0]
    c2 = {
        'total': int(tot_pb),
        'items': [
            {
                'id': str(row[0]),
                'nom': strip_ids(str(row[1])),
                'conditions': strip_ids(str(row[2])),
                'etapes': charge_json(row[3])
                if isinstance(row[3], str)
                else [],
                'scope': str(row[4]),
                'updated_at': str(row[5]),
            }
            for row in pb_rows
        ],
    }

    # C3 : Pièges (pitfalls)
    pf_rows = conn.execute(
        'SELECT id, statement, cost_observed, scope, created_at'
        ' FROM pitfalls ORDER BY rowid DESC LIMIT 20'
    ).fetchall()
    tot_pf = conn.execute('SELECT COUNT(*) FROM pitfalls').fetchone()[0]
    c3 = {
        'total': int(tot_pf),
        'items': [
            {
                'id': str(row[0]),
                'piege': strip_ids(str(row[1])),
                'cout': str(row[2]),
                'scope': str(row[3]),
                'created_at': str(row[4]),
            }
            for row in pf_rows
        ],
    }

    # C4 : Leçons
    les_rows = conn.execute(
        'SELECT id, statement, confidence, scope, status, confirm_count,'
        ' infirm_count, updated_at FROM lessons ORDER BY updated_at DESC LIMIT 30'
    ).fetchall()
    tot_les = conn.execute('SELECT COUNT(*) FROM lessons').fetchone()[0]
    c4 = {
        'total': int(tot_les),
        'items': [
            {
                'id': str(row[0]),
                'lecon': strip_ids(str(row[1])),
                'confiance': float(row[2]),
                'scope': str(row[3]),
                'statut': str(row[4]),
                'confirmations': int(row[5]),
                'infirmations': int(row[6]),
                'updated_at': str(row[7]),
            }
            for row in les_rows
        ],
    }

    # C5 : SERGE.md
    serge_md = get_summary(conn, 'serge_md') or {}
    c5 = {
        'version': int(serge_md.get('version') or 1),
        'content': strip_ids(str(serge_md.get('content') or '')),
        'previous': strip_ids(str(serge_md.get('previous') or '')),
        'updated_at': str(serge_md.get('updated_at') or ''),
    }

    return {'c1': c1, 'c2': c2, 'c3': c3, 'c4': c4, 'c5': c5}


def project_consolidation(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """État et cadence du moteur de consolidation (P4 Mémoire).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (rythme memory.consolidation_days).
        now: Maintenant ISO UTC.

    Returns:
        Dict {last_run, due, events}.
    """
    derniere = last_run(conn)
    est_due = due_for_consolidation(conn, policy, now)
    ev_rows = conn.execute(
        "SELECT ts, actor, type, payload_json FROM events WHERE actor='consolidate'"
        " OR type LIKE 'consolidate%' ORDER BY id DESC LIMIT 5"
    ).fetchall()
    return {
        'last_run': derniere,
        'due': est_due,
        'events': [
            {
                'ts': str(row[0]),
                'acteur': str(row[1]),
                'type': str(row[2]),
                'charge': charge_json(row[3]),
            }
            for row in ev_rows
        ],
    }


def project_requested(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Demandes d'évolution P3 des agents (P4 Mémoire).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{id, titre, etat, demande, contexte, point_llm, created_at}]}.
    """
    _ = (policy, now)
    rows = conn.execute(
        'SELECT id, title, state, payload_json, created_at FROM tickets'
        " WHERE type='REQUESTED' ORDER BY created_at DESC LIMIT 50"
    ).fetchall()
    items = []
    for row in rows:
        charge = charge_json(row[3])
        items.append(
            {
                'id': str(row[0]),
                'titre': strip_ids(str(row[1])),
                'etat': str(row[2]),
                'demande': strip_ids(str(charge.get('demande') or '')),
                'contexte': strip_ids(str(charge.get('contexte') or '')),
                'point_llm': str(charge.get('point_llm') or ''),
                'created_at': str(row[4]),
            }
        )
    return {'items': items}
