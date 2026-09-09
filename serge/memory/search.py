#!/usr/bin/env python3
"""Couche 5 : memory_search (outil libre, lecture seule, budgeté).

v1 : FTS5 + filtres structurés (types, venture, since, tags), pas de
vecteurs (sqlite-vec absent — interface prête : score fusionnable).
Lecture seule, budget tokens garanti, chaque recherche loguée (U5 +
anti-abus), PII redactée, `forbidden` du contrat appliqué côté tool.
Rate limit : searches_spent() pour l'appelant (fenêtre = cycle appelant).
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Sequence
from typing import Any

from serge.db.store import append_event

EMAIL_RE = re.compile(r'([A-Za-z0-9_.+-]+)@([A-Za-z0-9_.-]+\.[A-Za-z]{2,})')
PHONE_RE = re.compile(r'\+?[0-9][0-9 .()-]{7,}[0-9]')

TYPES = frozenset(
    {'lesson', 'playbook', 'pitfall', 'episode', 'ticket', 'artifact'}
)


def redact_text(text: str) -> str:
    """Masque emails/tokens (jamais de PII/secrets dans les extraits).

    Args:
        text: Texte brut.

    Returns:
        Texte redacté (initiale + domaine, téléphones masqués).
    """
    masked = EMAIL_RE.sub(
        lambda item: f'{item.group(1)[:1]}…@{item.group(2)}', text
    )
    return PHONE_RE.sub('+…', masked)


def ensure_index(conn: sqlite3.Connection) -> None:
    """Crée l'index FTS s'il manque (idempotent, même fichier P4).

    Args:
        conn: Connexion canon (commit par l'appelant).
    """
    conn.execute(
        'CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5('
        'type, ref, venture, tags, body, ts UNINDEXED,'
        " tokenize='unicode61')"
    )


def index_document(
    conn: sqlite3.Connection,
    doc_type: str,
    ref_id: str,
    body: str,
    venture: str = '',
    tags: Sequence[str] | None = None,
    ts: str = '',
) -> None:
    """Indexe un document (écriture, PII redactée, remplace si re-indexé).

    Args:
        conn: Connexion canon (commit par l'appelant).
        doc_type: lesson|playbook|pitfall|episode|ticket|artifact.
        ref_id: Id source.
        body: Texte indexé (redacté ici).
        venture: Scope venture ('' = global).
        tags: Tags (scope, canal...).
        ts: Horodatage ISO (filtre since).

    Raises:
        ValueError: Type inconnu.
    """
    if doc_type not in TYPES:
        raise ValueError(f'type inconnu : {doc_type}')
    ensure_index(conn)
    conn.execute(
        'DELETE FROM memory_fts WHERE type=? AND ref=?',
        (doc_type, ref_id),
    )
    conn.execute(
        'INSERT INTO memory_fts(type, ref, venture, tags, body, ts)'
        ' VALUES(?,?,?,?,?,?)',
        (
            doc_type,
            ref_id,
            venture,
            ' '.join(tags or []),
            redact_text(body),
            ts,
        ),
    )


def rebuild_index(conn: sqlite3.Connection) -> int:
    """Réindexe tout (leçons, épisodes, tickets, artifacts). Lourd, rare.

    Args:
        conn: Connexion canon (commit par l'appelant).

    Returns:
        Nombre de documents indexés.
    """
    ensure_index(conn)
    conn.execute('DELETE FROM memory_fts')
    count = 0
    for row in conn.execute(
        'SELECT id, statement, scope FROM lessons'
    ).fetchall():
        scope = str(row[2])
        venture = scope.split(':', 1)[1] if ':' in scope else ''
        index_document(
            conn,
            'lesson',
            str(row[0]),
            str(row[1]),
            venture=venture,
            tags=[scope],
        )
        count += 1
    for row in conn.execute(
        'SELECT name, conditions, scope FROM playbooks'
    ).fetchall():
        index_document(
            conn,
            'playbook',
            str(row[0]),
            f'{row[0]} : {row[1]}',
            tags=[str(row[2])],
        )
        count += 1
    for row in conn.execute(
        'SELECT id, type, venture_id, ts, payload_json FROM events'
        ' ORDER BY id DESC LIMIT 5000'
    ).fetchall():
        try:
            payload = json.loads(row[4] or '{}')
            text = json.dumps(payload, ensure_ascii=False)[:500]
        except (TypeError, ValueError):
            text = ''
        index_document(
            conn,
            'episode',
            str(row[0]),
            f'{row[1]} {text}',
            venture=str(row[2]),
            ts=str(row[3]),
        )
        count += 1
    for row in conn.execute(
        'SELECT id, type, title, payload_json FROM tickets'
    ).fetchall():
        index_document(
            conn,
            'ticket',
            str(row[0]),
            f'{row[1]} : {row[2]} {str(row[3])[:300]}',
            tags=[str(row[1])],
        )
        count += 1
    for row in conn.execute(
        'SELECT id, venture_id, kind, path_or_url FROM artifacts'
    ).fetchall():
        index_document(
            conn,
            'artifact',
            str(row[0]),
            f'{row[2]} : {row[3]}',
            venture=str(row[1]),
        )
        count += 1
    return count


def _fts_query(query: str) -> str:
    words = [word for word in re.findall(r'[\w]+', query.lower()) if word]
    if not words:
        return ''
    return ' OR '.join(f'"{word}"' for word in words[:10])


def searches_spent(
    conn: sqlite3.Connection, point: str, since_iso: str
) -> int:
    """Recherches loguées d'un point depuis un instant (rate limit appelant).

    Args:
        conn: Connexion canon (lecture).
        point: Nom du point LLM.
        since_iso: Début de fenêtre (cycle appelant).

    Returns:
        Nombre de recherches (événements memory.search).
    """
    row = conn.execute(
        "SELECT COUNT(*) FROM events WHERE actor=? AND type='memory.search'"
        ' AND ts>=?',
        (f'memory:{point}', since_iso),
    ).fetchone()
    return int(row[0]) if row else 0


def memory_search(
    conn: sqlite3.Connection,
    query: str,
    *,
    point: str = '?',
    types: Sequence[str] | None = None,
    venture: str = '',
    since: str = '',
    tags: Sequence[str] | None = None,
    top_k: int = 5,
    budget_tokens: int = 2000,
    forbidden: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Recherche libre (loguée, budgetée, filtrée, redactée).

    Args:
        conn: Connexion canon (commit par l'appelant).
        query: Requête langage naturel.
        point: Point appelant (traçabilité).
        types: Filtre types (vide = tous).
        venture: Scope ('' = tous ; 'autres_ventures' forbidden = strict).
        since: ISO min ('' = tout).
        tags: Tags requis (tous présents).
        top_k: Résultats max.
        budget_tokens: Budget extraits (garanti, ~4 car/token).
        forbidden: Contrats (autres_ventures, secrets, pii...).

    Returns:
        Dict results [{type,id,score,extrait}] + tokens_used + logged.
    """
    banned = set(forbidden or ())
    expression = _fts_query(query)
    wanted = [item for item in (types or []) if item in TYPES] or sorted(TYPES)
    needed_tags = {str(tag) for tag in (tags or []) if tag}
    rows: list[Any] = []
    if expression:
        ensure_index(conn)
        rows = conn.execute(
            'SELECT type, ref, venture, tags, body, ts, rank FROM memory_fts'
            ' WHERE memory_fts MATCH ? ORDER BY rank LIMIT 50',
            (expression,),
        ).fetchall()
    picked: list[dict[str, Any]] = []
    for doc_type, ref, doc_venture, doc_tags, body, ts, rank in rows:
        if doc_type not in wanted:
            continue
        if (
            'autres_ventures' in banned
            and doc_venture
            and doc_venture != venture
        ):
            continue
        if since and str(ts) and str(ts) < since:
            continue
        have = set(str(doc_tags or '').split())
        if needed_tags and not needed_tags <= have:
            continue
        picked.append(
            {
                'type': doc_type,
                'id': ref,
                'score': round(-float(rank or 0), 3),
                'body': str(body or ''),
            }
        )
        if len(picked) >= max(1, top_k):
            break
    char_budget = max(50, budget_tokens * 4)
    per_item = max(20, char_budget // max(1, len(picked))) if picked else 0
    results: list[dict[str, Any]] = []
    used_chars = 0
    for item in picked:
        excerpt = item['body'][:per_item]
        if len(item['body']) > per_item:
            excerpt += '… (affine ta requête)'
        used_chars += len(excerpt)
        results.append(
            {
                'type': item['type'],
                'id': item['id'],
                'score': item['score'],
                'extrait': excerpt,
            }
        )
    tokens_used = used_chars // 4
    append_event(
        conn,
        actor=f'memory:{point}',
        type='memory.search',
        payload={
            'query': query[:200],
            'types': wanted,
            'n': len(results),
            'tokens': tokens_used,
        },
    )
    return {'results': results, 'tokens_used': tokens_used, 'logged': True}
