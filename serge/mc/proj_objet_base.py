#!/usr/bin/env python3
"""Helpers partagés des fiches objet MC."""

from __future__ import annotations

import sqlite3
from typing import Any


def _row(
    conn: sqlite3.Connection, sql: str, args: tuple
) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, args).fetchone()


def _champs(paires: list[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{'k': k, 'v': '' if v is None else str(v)} for k, v in paires]


def _liens(items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [{'type': t, 'id': i, 'titre': titre} for t, i, titre in items]
