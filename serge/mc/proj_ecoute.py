#!/usr/bin/env python3
"""Projection de l'onglet Écoute (étape 1), lue en base."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.flow import trigger_refusal
from serge.interpreter.rules import quota_usage
from serge.mc.proj_etape import lister_invocations

ETAPE = 'pre_prospection'


def boutons_de_etape(
    conn: sqlite3.Connection, etape: str
) -> list[dict[str, Any]]:
    """Les déclencheurs « bouton » des invocations d'une étape.

    Chaque bouton dit quels champs du formulaire il transmet (paramètres
    de source ``form``), la question posée avant de le lancer, et où en
    sont les quotas dont il dépend. Exemple : ``{id, titre, champs:
    ['guide'], conditions: [{texte: 'Places de test occupées', occupe: 2,
    max: 3}], refus: ''}``.
    """
    boutons = []
    for trig_id, titre, inv_id, inv_titre, confirmer in conn.execute(
        'SELECT t.id, t.title, t.invocation_id, i.title, t.confirm_text'
        ' FROM triggers t JOIN invocations i ON i.id=t.invocation_id'
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
        conditions = []
        for (quota,) in conn.execute(
            'SELECT quota_id FROM trigger_conditions WHERE trigger_id=?'
            ' ORDER BY quota_id',
            (trig_id,),
        ).fetchall():
            usage = quota_usage(conn, str(quota))
            if usage is not None:
                conditions.append(
                    {'texte': usage[2], 'occupe': usage[0], 'max': usage[1]}
                )
        boutons.append(
            {
                'id': str(trig_id),
                'titre': str(titre or trig_id),
                'invocation': str(inv_id),
                'invocation_titre': str(inv_titre or inv_id),
                'champs': champs,
                'confirmer': str(confirmer or ''),
                'conditions': conditions,
                'refus': trigger_refusal(conn, str(trig_id)),
            }
        )
    return boutons


def _dernier_cycle(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """Le dernier cycle : ses pages par étiquette, ses fiches, sa note."""
    row = conn.execute(
        'SELECT id, guide, status, created_at, finished_at, choice_note'
        ' FROM listen_cycles ORDER BY created_at DESC, rowid DESC LIMIT 1'
    ).fetchone()
    if row is None:
        return None
    ident = str(row[0])
    pages = {
        str(label or 'pas encore triée'): int(n)
        for label, n in conn.execute(
            'SELECT label, COUNT(*) FROM listen_docs WHERE cycle_id=?'
            ' GROUP BY label ORDER BY label',
            (ident,),
        ).fetchall()
    }
    fiches = [
        {'id': str(v), 'titre': str(n), 'statut': str(s)}
        for v, n, s in conn.execute(
            'SELECT DISTINCT v.id, v.name, v.lifecycle FROM venture_sources s'
            ' JOIN ventures v ON v.id=s.venture_id'
            " WHERE s.cycle_id=? AND v.lifecycle IN ('CANDIDATE',"
            " 'POC_SELECTED') ORDER BY v.created_at",
            (ident,),
        ).fetchall()
    ]
    return {
        'id': ident,
        'guide': str(row[1]),
        'status': str(row[2]),
        'debut': str(row[3]),
        'fin': str(row[4]),
        'note': str(row[5]),
        'pages': pages,
        'fiches': fiches,
    }


def _flux(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Les flux suivis : pages ramenées, pages utiles, dernière lecture."""
    return [
        {
            'id': str(ident),
            'url': str(url),
            'titre': str(titre or url),
            'actif': bool(actif),
            'ajoute_par': str(par),
            'lu': str(lu),
            'pages': int(pages),
            'utiles': int(utiles),
        }
        for ident, url, titre, actif, par, lu, pages, utiles in conn.execute(
            'SELECT f.id, f.url, f.title, f.active, f.added_by,'
            ' f.last_read_at, COUNT(d.id), COALESCE(SUM(d.label IN'
            " ('besoin_nouveau', 'preuve', 'enrichit')), 0)"
            ' FROM listen_feeds f LEFT JOIN listen_docs d ON d.feed_id=f.id'
            ' GROUP BY f.id ORDER BY f.created_at, f.id'
        ).fetchall()
    ]


def project_ecoute(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Boutons, dernier cycle, flux, business de l'étape 1."""
    del policy, now_iso
    candidates = conn.execute(
        'SELECT id, name, lifecycle, choice_reason FROM ventures'
        " WHERE lifecycle IN ('CANDIDATE', 'POC_SELECTED')"
        ' ORDER BY updated_at DESC LIMIT 100'
    ).fetchall()
    return {
        'cycle': _dernier_cycle(conn),
        'candidates': [
            {
                'id': str(r[0]),
                'title': str(r[1]),
                'status': str(r[2]),
                'raison': str(r[3] or ''),
            }
            for r in candidates
        ],
        'flux': _flux(conn),
        'boutons': boutons_de_etape(conn, ETAPE),
        'invocations': [
            {'id': j['id'], 'titre': j['titre']}
            for j in lister_invocations(conn, ETAPE)
        ],
    }
