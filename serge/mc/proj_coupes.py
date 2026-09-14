#!/usr/bin/env python3
"""Projecteur P0 : état des coupe-circuits (Serge, étapes, kinds)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.coupe_circuit import etat_coupes
from serge.mc.libelles import KINDS


def project_coupes(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Trois nappes de coupe-circuits pour la page En direct.

    Args:
        conn: Canon.
        policy: Policy (ignorée, uniformité).
        now_iso: Maintenant ISO (ignoré : pas de temps dans le sig).

    Returns:
        ``{serge, etapes, kinds}`` (kinds portent un titre FR).
    """
    _ = (policy, now_iso)
    data = etat_coupes(conn)
    for kind in data['kinds']:
        ident = str(kind['id'])
        kind['titre'] = KINDS.get(ident, ident)
    return data
