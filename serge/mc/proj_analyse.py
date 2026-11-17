#!/usr/bin/env python3
"""Projecteurs P3 analyse : révisions des tickets, métriques."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from statistics import median
from typing import Any

from serge.mc.proj_outils import avant_iso, charge_json
from serge.text_ids import strip_ids


def project_metriques_tickets(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Métriques tickets E5 + §12 : volumes, approbation, délais (P3).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {semaine, backlog, approbation, rejets,
        auto_approbations, bypass, guichet, reponse_mediane_s}.
    """
    _ = policy
    semaine = avant_iso(now, hours=24 * 7)
    mois = avant_iso(now, hours=24 * 30)
    tickets_sem = conn.execute(
        'SELECT COUNT(*) FROM tickets WHERE created_at>=?', (semaine,)
    ).fetchone()[0]
    expir_sem = conn.execute(
        "SELECT COUNT(*) FROM ticket_events WHERE kind='transition.expired'"
        ' AND ts>=?',
        (semaine,),
    ).fetchone()[0]
    backlog = conn.execute(
        "SELECT COUNT(*) FROM tickets WHERE state IN ('OPEN','DISCUSSING')"
    ).fetchone()[0]
    verdicts: dict[str, dict[str, int]] = {}
    for row in conn.execute(
        'SELECT t.type, te.kind, COUNT(*) FROM ticket_events te'
        ' JOIN tickets t ON t.id=te.ticket_id WHERE te.kind IN'
        " ('transition.approved','transition.rejected') AND te.ts>=?"
        ' GROUP BY t.type, te.kind',
        (mois,),
    ).fetchall():
        verdicts.setdefault(str(row[0]), {})[str(row[1])] = int(row[2])
    par_type = {}
    approuves = rejetes = 0
    for typ, kinds in verdicts.items():
        ok = kinds.get('transition.approved', 0)
        ko = kinds.get('transition.rejected', 0)
        approuves += ok
        rejetes += ko
        par_type[typ] = ok / (ok + ko) if ok + ko else None
    taux_global = (
        approuves / (approuves + rejetes) if approuves + rejetes else None
    )
    auto = conn.execute(
        "SELECT COUNT(*) FROM ticket_events WHERE kind='transition.approved'"
        " AND actor='serge' AND ts>=?",
        (mois,),
    ).fetchone()[0]
    bypass = 0
    for row in conn.execute(
        "SELECT payload_json FROM ticket_events WHERE kind='transition.expired'"
        ' AND ts>=?',
        (mois,),
    ).fetchall():
        if charge_json(row[0]).get('default_applied'):
            bypass += 1
    guichet_rows = conn.execute(
        'SELECT te.kind, COUNT(*) FROM ticket_events te'
        " JOIN tickets t ON t.id=te.ticket_id WHERE t.type='GUICHET'"
        " AND te.kind IN ('transition.approved','transition.executed',"
        "'transition.expired') AND te.ts>=? GROUP BY te.kind",
        (mois,),
    ).fetchall()
    guichet_kinds = {str(r[0]): int(r[1]) for r in guichet_rows}
    resolus = guichet_kinds.get('transition.approved', 0) + guichet_kinds.get(
        'transition.executed', 0
    )
    reponse: dict[str, list[float]] = {}
    drafts = {}
    for row in conn.execute(
        'SELECT ticket_id, MIN(ts) FROM ticket_events WHERE kind LIKE'
        " 'transition.draft%' GROUP BY ticket_id"
    ).fetchall():
        drafts[str(row[0])] = str(row[1])
    for row in conn.execute(
        'SELECT te.ticket_id, t.type, MIN(te.ts) FROM ticket_events te'
        ' JOIN tickets t ON t.id=te.ticket_id WHERE te.kind IN'
        " ('transition.approved','transition.rejected','transition.executed')"
        ' AND te.ts>=? GROUP BY te.ticket_id, t.type',
        (mois,),
    ).fetchall():
        debut = drafts.get(str(row[0]))
        if not debut:
            continue
        deltas = (
            datetime.fromisoformat(str(row[2])) - datetime.fromisoformat(debut)
        ).total_seconds()
        reponse.setdefault(str(row[1]), []).append(max(0.0, deltas))
    medianes = {
        typ: int(median(deltas)) for typ, deltas in reponse.items() if deltas
    }
    return {
        'semaine': {
            'tickets': int(tickets_sem),
            'expirations': int(expir_sem),
        },
        'backlog': int(backlog),
        'approbation': {'taux_global': taux_global, 'par_type': par_type},
        'rejets': int(rejetes),
        'auto_approbations': int(auto),
        'bypass': int(bypass),
        'guichet': {
            'resolus': int(resolus),
            'expires': int(guichet_kinds.get('transition.expired', 0)),
        },
        'reponse_mediane_s': medianes,
    }


def project_diffs(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Les révisions des tickets tranchés en les modifiant (P3).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {versions: [{ticket_id, titre, versions: [{n, note, at}]}]}.
    """
    _ = (policy, now)
    versions = []
    for row in conn.execute(
        "SELECT id, title, versions_json FROM tickets WHERE versions_json<>''"
        " AND versions_json<>'[]' ORDER BY updated_at DESC LIMIT 20"
    ).fetchall():
        try:
            raw = json.loads(row[2] or '[]')
        except ValueError:
            raw = []
        notes = []
        if isinstance(raw, list):
            for entry in raw:
                if isinstance(entry, dict):
                    notes.append(
                        {
                            'n': entry.get('n'),
                            'note': entry.get('note'),
                            'at': entry.get('at'),
                        }
                    )
        versions.append(
            {
                'ticket_id': str(row[0]),
                'titre': strip_ids(str(row[1])),
                'versions': notes,
            }
        )
    return {'versions': versions}
