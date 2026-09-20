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


def current_cycle(
    conn: sqlite3.Connection, cycle_id: str
) -> dict[str, Any] | None:
    """Lit un cycle précis, sans exposer les autres cycles."""
    row = conn.execute(
        'SELECT id, guide, needs_target, business_target, status, created_at '
        'FROM listen_cycles WHERE id=?',
        (cycle_id,),
    ).fetchone()
    if row is None:
        return None
    return (
        dict(row)
        if isinstance(row, sqlite3.Row)
        else {
            'id': row[0],
            'guide': row[1],
            'needs_target': row[2],
            'business_target': row[3],
            'status': row[4],
            'created_at': row[5],
        }
    )


def cycle_documents(
    conn: sqlite3.Connection, cycle_id: str, limit: int = 200
) -> list[dict[str, Any]]:
    """Lit les pages du snapshot de cycle, dans leur ordre de collecte."""
    rows = conn.execute(
        'SELECT d.id, d.source, d.url, d.title, d.excerpt, d.published '
        'FROM listen_cycle_docs x JOIN listen_docs d ON d.id=x.doc_id '
        'WHERE x.cycle_id=? ORDER BY d.fetched_at, d.id LIMIT ?',
        (cycle_id, max(1, min(limit, 500))),
    ).fetchall()
    return [dict(row) for row in rows]


def known_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Lit les idées déjà persistées pour la déduplication inter-cycles."""
    rows = conn.execute(
        'SELECT id, title, content, observations, sellable_offer, '
        'normalized_key, status FROM business_candidates ORDER BY created_at'
    ).fetchall()
    return [dict(row) for row in rows]


def eligible_candidates(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Lit les idées sélectionnables, hors POC déjà engagés."""
    rows = conn.execute(
        'SELECT id, title, content, observations, sellable_offer, status '
        "FROM business_candidates WHERE status='CANDIDATE' ORDER BY created_at"
    ).fetchall()
    return [dict(row) for row in rows]


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


def read_named(
    conn: sqlite3.Connection,
    point_id: str,
    reader_id: str,
    args: Mapping[str, Any],
) -> dict[str, Any]:
    """Exécute un lecteur fermé après contrôle de permission DB."""
    from serge.db_readers import reader_allowed

    if not reader_allowed(conn, point_id, reader_id):
        return {'ok': False, 'code': 'permission_refusee', 'reader': reader_id}
    cycle_id = str(args.get('cycle_id') or '')
    if reader_id == 'current_listen_cycle':
        return {
            'ok': True,
            'reader': reader_id,
            'data': current_cycle(conn, cycle_id),
        }
    if reader_id == 'listen_cycle_documents':
        return {
            'ok': True,
            'reader': reader_id,
            'data': cycle_documents(conn, cycle_id),
        }
    if reader_id == 'known_business_candidates':
        return {
            'ok': True,
            'reader': reader_id,
            'data': known_candidates(conn),
        }
    if reader_id == 'eligible_poc_candidates':
        return {
            'ok': True,
            'reader': reader_id,
            'data': eligible_candidates(conn),
        }
    return {'ok': False, 'code': 'lecteur_inconnu', 'reader': reader_id}
