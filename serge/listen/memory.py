#!/usr/bin/env python3
"""Mémoire canonique de l'écoute : cycles, documents et candidats."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import utcnow


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


def _near_duplicate(
    conn: sqlite3.Connection, title: str, content: str
) -> bool:
    wanted = _tokens(title, content)
    if not wanted:
        return True
    for row in conn.execute(
        'SELECT title, content FROM business_candidates'
    ).fetchall():
        existing = _tokens(str(row[0]), str(row[1]))
        overlap = len(wanted & existing) / max(1, len(wanted | existing))
        if overlap >= 0.72:
            return True
    return False


def save_candidates(
    conn: sqlite3.Connection,
    cycle_id: str,
    data: Mapping[str, Any] | None,
    max_items: int | None = None,
) -> int:
    """Valide et écrit des candidats sans laisser le LLM écrire en DB."""
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
        if _near_duplicate(conn, title, content):
            continue
        evidence = item.get('evidence_ids')
        evidence = evidence if isinstance(evidence, list) else []
        evidence = [str(doc) for doc in evidence if str(doc) in allowed_docs]
        key = normalized_key(title, content)
        candidate_id = f'business-{key}'
        cursor = conn.execute(
            'INSERT OR IGNORE INTO business_candidates'
            '(id, title, content, observations, sellable_offer, '
            'normalized_key, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?)',
            (candidate_id, title, content, observations, offer, key, now, now),
        )
        for doc_id in evidence:
            conn.execute(
                'INSERT OR IGNORE INTO business_candidate_sources'
                '(candidate_id, doc_id, cycle_id) VALUES(?,?,?)',
                (candidate_id, doc_id, cycle_id),
            )
        if cursor.rowcount:
            saved += 1
    return saved


def select_poc(
    conn: sqlite3.Connection,
    cycle_id: str,
    data: Mapping[str, Any] | None,
    business_target: int,
) -> list[str]:
    """Applique la sélection avec veto DB contre tout POC déjà engagé."""
    raw = data.get('candidate_ids') if isinstance(data, Mapping) else None
    if not isinstance(raw, list):
        return []
    selected: list[str] = []
    for rank, raw_id in enumerate(raw[: max(0, business_target)], start=1):
        candidate_id = str(raw_id or '')
        row = conn.execute(
            "SELECT 1 FROM business_candidates WHERE id=? AND status='CANDIDATE'",
            (candidate_id,),
        ).fetchone()
        if row is None:
            continue
        try:
            conn.execute(
                'INSERT INTO poc_selections'
                '(id, cycle_id, candidate_id, rank, selected_at) '
                'VALUES(?,?,?,?,?)',
                (
                    f'{cycle_id}:{candidate_id}',
                    cycle_id,
                    candidate_id,
                    rank,
                    utcnow(),
                ),
            )
        except sqlite3.IntegrityError:
            continue
        conn.execute(
            "UPDATE business_candidates SET status='POC_SELECTED', updated_at=? "
            "WHERE id=? AND status='CANDIDATE'",
            (utcnow(), candidate_id),
        )
        selected.append(candidate_id)
    return selected
