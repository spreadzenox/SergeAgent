#!/usr/bin/env python3
"""Canon store helpers: open (0600), init, append-only events, UTC clock."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from serge.db.schema import init_schema
from serge.paths import system_root


def utcnow() -> str:
    """UTC timestamp ISO (canon clock, single format).

    Returns:
        Current UTC time as ISO-8601 string.
    """
    return datetime.now(UTC).isoformat()


def default_canon_path(root: Path | None = None) -> Path:
    """Chemin canon : <system_root>/state/serge.db.

    Args:
        root: system_root (défaut : SERGE_SYSTEM_ROOT).

    Returns:
        Chemin du fichier canon.
    """
    base = root or system_root()
    return base / 'state/serge.db'


def open_db(path: Path) -> sqlite3.Connection:
    """Open (creating) the canon DB: schema ensured, 0600, WAL.

    Args:
        path: DB file (parent created, mode 0600 enforced).

    Returns:
        SQLite connection with Row factory.
    """
    fresh = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA journal_mode=WAL')
    connection.execute('PRAGMA foreign_keys=ON')
    init_schema(connection)
    connection.commit()
    if fresh:
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return connection


def append_event(
    connection: sqlite3.Connection,
    *,
    actor: str,
    type: str,
    venture_id: str = '',
    payload: dict[str, Any] | None = None,
    links: dict[str, Any] | None = None,
) -> int:
    """Append one episode (couche 2). Never modifies history.

    Args:
        connection: Open canon connection (committed by caller).
        actor: scheduler, guard, point name, ticket id, owner...
        type: Event type (transition.*, touch.*, decision.*...).
        venture_id: Scope, '' when global.
        payload: Event facts (JSON).
        links: Related ids (JSON).

    Returns:
        Row id of the appended event.
    """
    cursor = connection.execute(
        'INSERT INTO events(ts, actor, venture_id, type, payload_json,'
        ' links_json) VALUES(?,?,?,?,?,?)',
        (
            utcnow(),
            actor,
            venture_id,
            type,
            json.dumps(payload or {}, ensure_ascii=False),
            json.dumps(links or {}, ensure_ascii=False),
        ),
    )
    return int(cursor.lastrowid or 0)
