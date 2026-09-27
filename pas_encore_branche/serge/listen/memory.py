#!/usr/bin/env python3
"""Mémoire de l'étape 1 : cycles, pages figées, business trouvés et choisis."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event, utcnow


def _cycle_id() -> str:
    return f'listen-{uuid.uuid4().hex}'


def create_cycle(
    conn: sqlite3.Connection,
    guide: str,
    needs_target: int,
    business_target: int,
) -> str:
    """Crée un cycle et fige uniquement les documents jamais explorés."""
    if needs_target < 1 or business_target < 1:
        raise ValueError('paramètres d’écoute invalides')
    cycle_id = _cycle_id()
    now = utcnow()
    conn.execute(
        'INSERT INTO listen_cycles'
        '(id, guide, needs_target, business_target, created_at) '
        'VALUES(?,?,?,?,?)',
        (cycle_id, guide[:4000], needs_target, business_target, now),
    )
    conn.execute(
        'INSERT INTO listen_cycle_docs(cycle_id, doc_id) '
        'SELECT ?, d.id FROM listen_docs d '
        'WHERE NOT EXISTS (SELECT 1 FROM listen_cycle_docs x '
        'WHERE x.doc_id=d.id)',
        (cycle_id,),
    )
    return cycle_id


def normalized_key(title: str, content: str) -> str:
    """Produit une clé stable de rapprochement, sans décision LLM."""
    raw = ' '.join(sorted(f'{title} {content}'.lower().split()))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]


def _tokens(title: str, content: str) -> set[str]:
    return set(f'{title} {content}'.lower().split())


def _near_duplicate(conn: sqlite3.Connection, title: str, content: str) -> str:
    """Id du business existant trop proche, ou ``''``.

    Exemple : deux fiches qui partagent au moins 72 % de leurs mots sont
    considérées comme le même business.
    """
    wanted = _tokens(title, content)
    if not wanted:
        return '(vide)'
    for row in conn.execute(
        'SELECT id, name, description FROM ventures'
    ).fetchall():
        existing = _tokens(str(row[1]), str(row[2]))
        overlap = len(wanted & existing) / max(1, len(wanted | existing))
        if overlap >= 0.72:
            return str(row[0])
    return ''


def save_candidates(
    conn: sqlite3.Connection,
    cycle_id: str,
    data: Mapping[str, Any] | None,
    max_items: int | None = None,
) -> int:
    """Écrit les fiches valides comme business ``CANDIDATE``.

    Le LLM n'écrit jamais en base : ce code vérifie chaque fiche, écarte les
    doublons et note chaque fiche écartée dans le journal.
    """
    items = data.get('needs') if isinstance(data, Mapping) else None
    if not isinstance(items, list):
        return 0
    allowed_docs = {
        str(row[0])
        for row in conn.execute(
            'SELECT doc_id FROM listen_cycle_docs WHERE cycle_id=?',
            (cycle_id,),
        )
    }
    now = utcnow()
    saved = 0
    limit = len(items) if max_items is None else max(0, max_items)
    for item in items[:limit]:
        if not isinstance(item, Mapping):
            continue
        title = str(item.get('title') or '').strip()[:240]
        content = str(item.get('content') or item.get('need') or '').strip()
        offer = str(item.get('sellable_offer') or '').strip()
        observations = str(item.get('observations') or '').strip()
        if not title or not content:
            continue
        proche = _near_duplicate(conn, title, content)
        if proche:
            append_event(
                conn,
                actor='listen.dedup',
                type='listen.candidate_rejected',
                payload={
                    'cycle_id': cycle_id,
                    'title': title,
                    'reason': 'doublon',
                    'similar_venture_id': proche,
                },
            )
            continue
        evidence = item.get('evidence_ids')
        evidence = evidence if isinstance(evidence, list) else []
        evidence = [str(doc) for doc in evidence if str(doc) in allowed_docs]
        key = normalized_key(title, content)
        venture_id = f'business-{key}'
        cursor = conn.execute(
            'INSERT OR IGNORE INTO ventures(id, name, lifecycle, schedulable,'
            ' description, observations, sellable_offer, dedup_key,'
            " created_at, updated_at) VALUES(?,?,'CANDIDATE',0,?,?,?,?,?,?)",
            (venture_id, title, content, observations, offer, key, now, now),
        )
        for doc_id in evidence:
            conn.execute(
                'INSERT OR IGNORE INTO venture_sources'
                '(venture_id, doc_id, cycle_id) VALUES(?,?,?)',
                (venture_id, doc_id, cycle_id),
            )
        if cursor.rowcount:
            saved += 1
            append_event(
                conn,
                actor='listen.dedup',
                type='venture.candidate',
                venture_id=venture_id,
                payload={'cycle_id': cycle_id, 'evidence': evidence},
            )
    return saved


def select_poc(
    conn: sqlite3.Connection,
    cycle_id: str,
    data: Mapping[str, Any] | None,
    business_target: int,
) -> list[str]:
    """Passe les business choisis en ``POC_SELECTED``.

    Refuse, et note dans le journal, tout identifiant inconnu ou tout
    business qui n'est plus ``CANDIDATE`` (déjà en test, par exemple).
    """
    raw = data.get('candidate_ids') if isinstance(data, Mapping) else None
    if not isinstance(raw, list):
        return []
    selected: list[str] = []
    for rank, raw_id in enumerate(raw[: max(0, business_target)], start=1):
        venture_id = str(raw_id or '')
        cursor = conn.execute(
            "UPDATE ventures SET lifecycle='POC_SELECTED', updated_at=?"
            " WHERE id=? AND lifecycle='CANDIDATE'",
            (utcnow(), venture_id),
        )
        if not cursor.rowcount:
            append_event(
                conn,
                actor='listen.veto',
                type='listen.selection_refused',
                venture_id=venture_id,
                payload={'cycle_id': cycle_id, 'reason': 'pas_candidate'},
            )
            continue
        append_event(
            conn,
            actor='listen.veto',
            type='venture.poc_selected',
            venture_id=venture_id,
            payload={'cycle_id': cycle_id, 'rank': rank},
        )
        selected.append(venture_id)
    return selected
