#!/usr/bin/env python3
"""Projection de l'onglet Écoute (étape 1), lue en base."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.proj_etape import lister_invocations

ETAPE = 'pre_prospection'


def boutons_de_etape(
    conn: sqlite3.Connection, etape: str
) -> list[dict[str, Any]]:
    """Les déclencheurs « bouton » des invocations d'une étape.

    Chaque bouton dit quels champs du formulaire il transmet (paramètres
    de source ``form``). Exemple : ``{id, titre, invocation, champs:
    ['guide']}``.
    """
    boutons = []
    for trig_id, titre, inv_id, inv_titre in conn.execute(
        'SELECT t.id, t.title, t.invocation_id, i.title FROM triggers t'
        ' JOIN invocations i ON i.id=t.invocation_id'
        " WHERE t.event='button' AND t.enabled=1 AND t.deleted_at=''"
        " AND i.step_id=? AND i.deleted_at='' ORDER BY t.id",
        (etape,),
    ).fetchall():
        champs = [
            str(r[0])
            for r in conn.execute(
                'SELECT value FROM trigger_params WHERE trigger_id=?'
                " AND source='form' ORDER BY param_name",
                (trig_id,),
            ).fetchall()
        ]
        boutons.append(
            {
                'id': str(trig_id),
                'titre': str(titre or trig_id),
                'invocation': str(inv_id),
                'invocation_titre': str(inv_titre or inv_id),
                'champs': champs,
            }
        )
    return boutons


def project_ecoute(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Dernier cycle, candidats, boutons et invocations de l'étape 1."""
    del policy, now_iso
    cycle = conn.execute(
        'SELECT id, guide, needs_target, business_target, status, created_at, '
        'started_at, finished_at FROM listen_cycles ORDER BY created_at DESC LIMIT 1'
    ).fetchone()
    candidates = conn.execute(
        'SELECT id, name AS title, sellable_offer, lifecycle AS status,'
        " updated_at FROM ventures WHERE lifecycle IN ('CANDIDATE',"
        " 'POC_SELECTED')"
        ' ORDER BY updated_at DESC LIMIT 100'
    ).fetchall()
    cols = ('id', 'guide', 'needs_target', 'business_target', 'status')
    return {
        'cycle': dict(zip(cols, cycle, strict=False)) if cycle else None,
        'candidates': [
            {'id': str(r[0]), 'title': str(r[1]), 'status': str(r[3])}
            for r in candidates
        ],
        'boutons': boutons_de_etape(conn, ETAPE),
        'invocations': [
            {'id': j['id'], 'titre': j['titre']}
            for j in lister_invocations(conn, ETAPE)
        ],
    }
