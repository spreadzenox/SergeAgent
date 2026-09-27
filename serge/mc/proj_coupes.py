#!/usr/bin/env python3
"""Projecteur P0 : les coupe-circuits (Serge, étapes, files, invocations)."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.coupe_circuit import etat_coupes


def project_coupes(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Les coupe-circuits pour la page En direct.

    Args:
        conn: Connexion à la base.
        policy: Policy (ignorée, uniformité).
        now_iso: Maintenant ISO (ignoré : pas de temps dans le sig).

    Returns:
        ``{serge, etapes, files, invocations}``.
    """
    _ = (policy, now_iso)
    return etat_coupes(conn)
