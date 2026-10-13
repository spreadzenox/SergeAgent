#!/usr/bin/env python3
"""Le catalogue des connecteurs : un point d'entrée par outil, rempli
depuis ``pipeline.yaml`` (section ``tools``, clé ``api``).

À part de ``appel.py`` : le remplissage de la base ne doit pas importer ce
qui écrit au journal (pas d'import circulaire, charte partie 2).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any


def seed_api(
    conn: sqlite3.Connection, tool_id: str, spec: Mapping[str, Any]
) -> None:
    """Le point d'entrée d'un outil ``call_api``, depuis ``pipeline.yaml``."""
    conn.execute(
        'INSERT OR IGNORE INTO api_endpoints(tool_id, service_id, method,'
        ' path) VALUES(?,?,?,?)',
        (
            tool_id,
            str(spec['service']),
            str(spec['method']).upper(),
            str(spec['path']),
        ),
    )
    for position, param in enumerate(spec.get('params') or []):
        conn.execute(
            'INSERT OR IGNORE INTO api_endpoint_params(tool_id, name, type,'
            ' required, description, position) VALUES(?,?,?,?,?,?)',
            (
                tool_id,
                str(param['name']),
                str(param.get('type', 'text')),
                int(bool(param.get('required', False))),
                str(param.get('description', '')),
                position,
            ),
        )
