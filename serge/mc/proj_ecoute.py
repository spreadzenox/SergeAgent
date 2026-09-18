#!/usr/bin/env python3
"""Projection DB de l'onglet Mission Control Écoute."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.db_readers import readers_du_point


def project_ecoute(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Retourne réglages, dernier cycle, candidats et permissions."""
    del now_iso
    listen = dict(policy.get('listen') or {})
    cycle = conn.execute(
        'SELECT id, guide, needs_target, business_target, status, created_at, '
        'started_at, finished_at FROM listen_cycles ORDER BY created_at DESC LIMIT 1'
    ).fetchone()
    candidates = conn.execute(
        'SELECT id, title, sellable_offer, status, updated_at '
        'FROM business_candidates ORDER BY updated_at DESC LIMIT 100'
    ).fetchall()
    return {
        'settings': {
            'discovery_needs_target': listen.get('discovery_needs_target'),
            'poc_business_target': listen.get('poc_business_target'),
        },
        'cycle': dict(cycle) if cycle else None,
        'candidates': [dict(row) for row in candidates],
        'agents': [
            {
                'id': point,
                'readers': readers_du_point(conn, point),
            }
            for point in (
                'listen_discover_needs_a',
                'listen_discover_needs_b',
                'listen_choose_poc',
            )
        ],
    }
