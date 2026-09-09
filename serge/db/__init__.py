#!/usr/bin/env python3
"""Canon v2: SQLite authority (registres, épisodes, tickets, leçons)."""

from __future__ import annotations

from serge.db.schema import SCHEMA_VERSION, TABLES, init_schema
from serge.db.store import append_event, default_canon_path, open_db, utcnow

__all__ = [
    'SCHEMA_VERSION',
    'TABLES',
    'append_event',
    'default_canon_path',
    'init_schema',
    'open_db',
    'utcnow',
]
