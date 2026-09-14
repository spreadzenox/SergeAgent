#!/usr/bin/env python3
"""Migration v8 : etape_id sur les work items + 8 sacs de vie du projet."""

from __future__ import annotations

import json
import sqlite3

from serge.etapes import KIND_DEFAUT, SEED, enabled_depuis_v7, etape_pour_kind


def apply_v008(connection: sqlite3.Connection) -> None:
    """Ajoute ``work_items.etape_id``, remappe les étapes.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    cols = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(work_items)')
    }
    if 'etape_id' not in cols:
        connection.execute(
            'ALTER TABLE work_items ADD COLUMN etape_id'
            " TEXT NOT NULL DEFAULT ''"
        )
    for kind, etape in KIND_DEFAUT.items():
        connection.execute(
            "UPDATE work_items SET etape_id=? WHERE etape_id='' AND kind=?",
            (etape, kind),
        )
    for row in connection.execute(
        "SELECT id, kind FROM work_items WHERE etape_id=''"
    ).fetchall():
        fallback = etape_pour_kind(str(row[1]))
        if fallback:
            connection.execute(
                'UPDATE work_items SET etape_id=? WHERE id=?',
                (fallback, row[0]),
            )
    anciens = {
        str(row[0]): int(row[1])
        for row in connection.execute('SELECT id, enabled FROM pipeline_steps')
    }
    connection.execute('DELETE FROM pipeline_steps')
    for ident, rang, kinds in SEED:
        connection.execute(
            'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang)'
            ' VALUES(?,?,?,?)',
            (
                ident,
                enabled_depuis_v7(anciens, ident),
                json.dumps(list(kinds), ensure_ascii=False),
                rang,
            ),
        )
