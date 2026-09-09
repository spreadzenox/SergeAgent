#!/usr/bin/env python3
"""Oubli épisodes (D §9) : archive froide réversible, jamais d'effacement.

Épisodes > N jours ET non référencés par une leçon → JSONL.gz sous
state/archive/ + manifest canon (episode_archives) + retrait DB live.
Acte de gouvernance logué (appelant : FYI). Réimport possible.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from serge.db.store import utcnow


def _referenced_ids(conn: sqlite3.Connection) -> set[str]:
    refs: set[str] = set()
    for row in conn.execute('SELECT sources_json FROM lessons').fetchall():
        try:
            sources = json.loads(row[0] or '[]')
        except (TypeError, ValueError):
            continue
        if isinstance(sources, list):
            refs.update(str(item) for item in sources)
    return refs


def archive_episodes(
    conn: sqlite3.Connection,
    archive_dir: Path,
    days: int,
    now: str | None = None,
) -> dict[str, Any]:
    """Archive les épisodes vieux + orphelins (gzip + manifest + retrait).

    Args:
        conn: Connexion canon (commit par l'appelant).
        archive_dir: Dossier state/archive (créé, 0700).
        days: Âge min (policy memory.episode_archive_days).
        now: ISO (défaut : maintenant).

    Returns:
        Dict path/count/sha256 (count 0 = rien à faire, path '').
    """
    moment = now or utcnow()
    cutoff = (
        datetime.fromisoformat(moment) - timedelta(days=days)
    ).isoformat()
    refs = _referenced_ids(conn)
    rows = conn.execute(
        'SELECT id, ts, actor, venture_id, type, payload_json, links_json'
        ' FROM events WHERE ts<? ORDER BY id ASC LIMIT 5000',
        (cutoff,),
    ).fetchall()
    movable = [row for row in rows if str(row[0]) not in refs]
    if not movable:
        return {'path': '', 'count': 0, 'sha256': ''}
    archive_dir.mkdir(parents=True, exist_ok=True)
    try:
        archive_dir.chmod(0o700)
    except OSError:
        pass
    stamp = datetime.fromisoformat(moment).strftime('%Y%m%dT%H%M%S')
    dest = archive_dir / f'episodes_{stamp}.jsonl.gz'
    lines = [
        json.dumps(
            {
                'id': row[0],
                'ts': row[1],
                'actor': row[2],
                'venture_id': row[3],
                'type': row[4],
                'payload': json.loads(row[5] or '{}'),
                'links': json.loads(row[6] or '{}'),
            },
            ensure_ascii=False,
        )
        for row in movable
    ]
    raw = ('\n'.join(lines) + '\n').encode('utf-8')
    dest.write_bytes(gzip.compress(raw))
    try:
        dest.chmod(0o600)
    except OSError:
        pass
    digest = hashlib.sha256(raw).hexdigest()
    ids = [row[0] for row in movable]
    conn.execute(
        f'DELETE FROM events WHERE id IN ({",".join("?" * len(ids))})',
        ids,
    )
    conn.execute(
        'INSERT INTO episode_archives(path, period, count, sha256,'
        ' created_at) VALUES(?,?,?,?,?)',
        (str(dest), cutoff[:10], len(movable), digest, moment),
    )
    return {'path': str(dest), 'count': len(movable), 'sha256': digest}
