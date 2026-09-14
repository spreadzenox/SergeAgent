#!/usr/bin/env python3
"""Canon v2: SQLite authority (registres, épisodes, tickets, leçons)."""

from __future__ import annotations

from serge.db.boot import init_schema
from serge.db.migrate import MigrateError, apply_pending, read_version
from serge.db.schema import SCHEMA_VERSION, TABLES
from serge.db.store import append_event, default_canon_path, open_db, utcnow

__all__ = [
    'MigrateError',
    'SCHEMA_VERSION',
    'TABLES',
    'append_event',
    'apply_pending',
    'default_canon_path',
    'init_schema',
    'open_db',
    'read_version',
    'utcnow',
]
