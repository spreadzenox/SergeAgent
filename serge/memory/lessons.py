#!/usr/bin/env python3
"""Couche 3 : leçons/playbooks/pitfalls (distillé, actionnable).

Cycle : candidate → active → deprecated (3 infirmations ou expiry).
Jamais effacé. Confiance bayésienne simplifiée. Scope : global |
venture:<id> | canal:<nom>. Top-k : scope exact > canal > global,
puis mots-clés, puis confiance. Tags v1 = mots du statement.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from serge.db.store import utcnow

STATUSES = frozenset({'candidate', 'active', 'deprecated'})
DEFAULT_DEPRECATE = 3


def _new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


def add_lesson(
    conn: sqlite3.Connection,
    statement: str,
    *,
    confidence: float = 0.5,
    scope: str = 'global',
    sources: list[str] | None = None,
    created_by: str = '',
    expires_at: str = '',
) -> str:
    """Crée une leçon candidate (écriture consolidateur validé/ticket).

    Args:
        conn: Connexion canon (commit par l'appelant).
        statement: Énoncé actionnable.
        confidence: Confiance initiale 0-1.
        scope: global | venture:<id> | canal:<nom>.
        sources: Ids épisodes sources.
        created_by: consolidateur | owner.
        expires_at: ISO ou '' (jamais).

    Returns:
        L'id de la leçon.
    """
    lesson_id = _new_id('l')
    moment = utcnow()
    conn.execute(
        'INSERT INTO lessons(id, statement, confidence, scope, status,'
        ' sources_json, created_by, confirm_count, infirm_count,'
        ' expires_at, created_at, updated_at)'
        " VALUES(?,?,?,?,'candidate',?,?,?,?,?,?,?)",
        (
            lesson_id,
            statement,
            max(0.0, min(1.0, confidence)),
            scope,
            json.dumps(sources or [], ensure_ascii=False),
            created_by,
            0,
            0,
            expires_at,
            moment,
            moment,
        ),
    )
    return lesson_id


def set_lesson_status(
    conn: sqlite3.Connection, lesson_id: str, status: str
) -> None:
    """Change le statut (candidate|active|deprecated).

    Raises:
        ValueError: Statut inconnu ou leçon absente.
    """
    if status not in STATUSES:
        raise ValueError(f'statut inconnu : {status}')
    cursor = conn.execute(
        'UPDATE lessons SET status=?, updated_at=? WHERE id=?',
        (status, utcnow(), lesson_id),
    )
    if not cursor.rowcount:
        raise ValueError(f'leçon inconnue : {lesson_id}')


def confirm_lesson(conn: sqlite3.Connection, lesson_id: str) -> float:
    """Confirme (+1, confiance → 1). Retourne la confiance.

    Raises:
        ValueError: Leçon absente.
    """
    row = conn.execute(
        'SELECT confidence, confirm_count FROM lessons WHERE id=?',
        (lesson_id,),
    ).fetchone()
    if not row:
        raise ValueError(f'leçon inconnue : {lesson_id}')
    confidence = 1.0 - (1.0 - float(row[0])) * 0.8
    conn.execute(
        'UPDATE lessons SET confidence=?, confirm_count=?, updated_at=?'
        ' WHERE id=?',
        (round(confidence, 4), int(row[1]) + 1, utcnow(), lesson_id),
    )
    return round(confidence, 4)


def infirm_lesson(
    conn: sqlite3.Connection,
    lesson_id: str,
    deprecate_after: int = DEFAULT_DEPRECATE,
) -> dict[str, Any]:
    """Infirme (−1, confiance × 0.7, deprecated à N).

    Args:
        conn: Connexion canon (commit par l'appelant).
        lesson_id: Leçon infirmée.
        deprecate_after: Seuil infirmations (policy).

    Returns:
        Dict confiance/infirm_count/status.

    Raises:
        ValueError: Leçon absente.
    """
    row = conn.execute(
        'SELECT confidence, infirm_count FROM lessons WHERE id=?',
        (lesson_id,),
    ).fetchone()
    if not row:
        raise ValueError(f'leçon inconnue : {lesson_id}')
    infirm = int(row[1]) + 1
    confidence = round(float(row[0]) * 0.7, 4)
    status = 'deprecated' if infirm >= max(1, deprecate_after) else None
    if status:
        conn.execute(
            'UPDATE lessons SET confidence=?, infirm_count=?, status=?,'
            ' updated_at=? WHERE id=?',
            (confidence, infirm, status, utcnow(), lesson_id),
        )
    else:
        conn.execute(
            'UPDATE lessons SET confidence=?, infirm_count=?, updated_at=?'
            ' WHERE id=?',
            (confidence, infirm, utcnow(), lesson_id),
        )
        current = conn.execute(
            'SELECT status FROM lessons WHERE id=?', (lesson_id,)
        ).fetchone()
        status = str(current[0])
    return {
        'confiance': confidence,
        'infirm_count': infirm,
        'status': status,
    }


def expire_lessons(
    conn: sqlite3.Connection, now: str | None = None
) -> list[str]:
    """Déprécie les leçons expirées (gouvernance loguée par l'appelant).

    Args:
        conn: Connexion canon (commit par l'appelant).
        now: ISO (défaut : maintenant).

    Returns:
        Ids dépréciés.
    """
    moment = now or utcnow()
    rows = conn.execute(
        "SELECT id FROM lessons WHERE expires_at<>'' AND expires_at<=?"
        " AND status<>'deprecated'",
        (moment,),
    ).fetchall()
    expired = [str(row[0]) for row in rows]
    for lesson_id in expired:
        set_lesson_status(conn, lesson_id, 'deprecated')
    return expired


def _scope_rank(scope: str, venture_id: str, canal: str) -> int:
    if venture_id and scope == f'venture:{venture_id}':
        return 0
    if canal and scope == f'canal:{canal}':
        return 1
    if scope == 'global':
        return 2
    return 3


def top_lessons(
    conn: sqlite3.Connection,
    query_words: list[str] | None = None,
    *,
    venture_id: str = '',
    canal: str = '',
    k: int = 3,
    include_deprecated: bool = False,
    now: str | None = None,
) -> list[dict[str, Any]]:
    """Top-k leçons (scope > mots-clés > confiance, expirées exclues).

    Args:
        conn: Connexion canon (lecture).
        query_words: Mots recherchés (statement).
        venture_id: Scope venture exact d'abord.
        canal: Scope canal ensuite.
        k: Nombre max.
        include_deprecated: Inclure les dépréciées (explicite seul).
        now: ISO (défaut : maintenant).

    Returns:
        Leçons triées (id, statement, confidence, scope, status).
    """
    moment = now or utcnow()
    query = [str(word).lower() for word in (query_words or []) if word]
    clauses = ["(expires_at='' OR expires_at>?)"]
    params: list[Any] = [moment]
    if not include_deprecated:
        clauses.append("status<>'deprecated'")
    rows = conn.execute(
        'SELECT id, statement, confidence, scope, status FROM lessons'
        f' WHERE {" AND ".join(clauses)}',
        params,
    ).fetchall()
    scored: list[tuple[int, int, float, dict[str, Any]]] = []
    for row in rows:
        lesson = {
            'id': row[0],
            'statement': row[1],
            'confidence': float(row[2]),
            'scope': row[3],
            'status': row[4],
        }
        lowered = str(row[1]).lower()
        hits = sum(1 for word in query if word in lowered)
        scored.append(
            (
                _scope_rank(str(row[3]), venture_id, canal),
                -hits,
                -float(row[2]),
                lesson,
            )
        )
    scored.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in scored[: max(0, k)]]


def add_playbook(
    conn: sqlite3.Connection,
    name: str,
    conditions: str = '',
    steps: list[str] | None = None,
    scope: str = 'global',
) -> str:
    """Crée un playbook (procédure qui marche + conditions).

    Returns:
        L'id du playbook.
    """
    book_id = _new_id('pb')
    moment = utcnow()
    conn.execute(
        'INSERT INTO playbooks(id, name, conditions, steps_json, scope,'
        ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
        (
            book_id,
            name,
            conditions,
            json.dumps(steps or [], ensure_ascii=False),
            scope,
            moment,
            moment,
        ),
    )
    return book_id


def add_pitfall(
    conn: sqlite3.Connection,
    statement: str,
    cost_observed: str = '',
    scope: str = 'global',
) -> str:
    """Crée un pitfall (échec typé + coût observé).

    Returns:
        L'id du pitfall.
    """
    pit_id = _new_id('pf')
    conn.execute(
        'INSERT INTO pitfalls(id, statement, cost_observed, scope,'
        ' created_at) VALUES(?,?,?,?,?)',
        (pit_id, statement, cost_observed, scope, utcnow()),
    )
    return pit_id
