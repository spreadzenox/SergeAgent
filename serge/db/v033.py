#!/usr/bin/env python3
"""Migration v33 : les réglages généraux passent dans des tables.

Avant, la policy était une copie complète en JSON à chaque modification
(``policy_snapshots``). Maintenant, chaque réglage est une ligne
(décision Q68) :

- ``policy_sections`` : les familles de réglages de la page Policy (titre,
  pourquoi, et un verrou éventuel : « pas pendant qu'une ligne de
  ``campaigns`` a ``state`` = ``RUNNING`` ») ;
- ``policy_settings`` : un réglage par ligne, avec sa valeur (en JSON), son
  titre, son aide, sa sorte (``eur``, ``curseur``, ``liste``…), ses bornes,
  ses choix, et **sa valeur précédente** (qui l'a remplacée, quand) pour le
  bouton « Remettre la valeur précédente » ;
- ``policy_relations`` : « tel réglage ≤ tel autre » (strict ou non).
  Exemple : le plancher du capital ne dépasse pas son plafond.

Les valeurs en vigueur (le dernier snapshot) sont reprises telles quelles ;
leur titre, leur aide et leurs bornes viennent ensuite de
``config/policy.yaml`` (``serge/policy_store.py``). Puis la table des
snapshots est effacée.

Les réglages des invocations et les quotas des tables gardent aussi leur
valeur précédente (trois colonnes de plus).
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any

SCRIPT = """
CREATE TABLE IF NOT EXISTS policy_sections (
    id TEXT PRIMARY KEY,
    position INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    why TEXT NOT NULL DEFAULT '',
    lock_table TEXT NOT NULL DEFAULT '',
    lock_column TEXT NOT NULL DEFAULT '',
    lock_value TEXT NOT NULL DEFAULT '',
    lock_reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS policy_settings (
    id TEXT PRIMARY KEY,
    section_id TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    help TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT '',
    value_json TEXT NOT NULL,
    min_value REAL,
    max_value REAL,
    step REAL,
    choices_json TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT '',
    previous_json TEXT NOT NULL DEFAULT '',
    previous_at TEXT NOT NULL DEFAULT '',
    previous_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS policy_relations (
    lower_id TEXT NOT NULL,
    upper_id TEXT NOT NULL,
    strict INTEGER NOT NULL DEFAULT 0 CHECK (strict IN (0, 1)),
    PRIMARY KEY (lower_id, upper_id)
);
"""


def _leaves(node: dict[str, Any], prefix: str = ''):
    """``('budget.monthly_eur', 50.0)`` pour chaque valeur du snapshot."""
    for key, value in node.items():
        path = f'{prefix}{key}'
        if isinstance(value, dict):
            yield from _leaves(value, f'{path}.')
        elif path != 'schema_version':
            yield path, value


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    }


def apply_v033(connection: sqlite3.Connection) -> None:
    """Crée les tables des réglages, reprend les valeurs en vigueur."""
    connection.executescript(SCRIPT)
    tables = {
        str(r[0])
        for r in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    if 'policy_snapshots' in tables:
        row = connection.execute(
            'SELECT content_json, applied_by, active_from'
            ' FROM policy_snapshots ORDER BY id DESC LIMIT 1'
        ).fetchone()
        content = json.loads(row[0]) if row else {}
        for ident, value in _leaves(
            content if isinstance(content, dict) else {}
        ):
            connection.execute(
                'INSERT OR IGNORE INTO policy_settings(id, value_json,'
                ' updated_at, updated_by) VALUES(?,?,?,?)',
                (ident, json.dumps(value), str(row[2]), str(row[1])),
            )
        connection.execute('DROP TABLE policy_snapshots')
    for table, kind in (
        ('invocation_settings', "TEXT NOT NULL DEFAULT ''"),
        ('table_quotas', 'INTEGER'),
    ):
        have = _columns(connection, table)
        for column, sql_type in (
            ('previous_value', kind),
            ('previous_at', "TEXT NOT NULL DEFAULT ''"),
            ('previous_by', "TEXT NOT NULL DEFAULT ''"),
        ):
            if column not in have:
                connection.execute(
                    f'ALTER TABLE {table} ADD COLUMN {column} {sql_type}'
                )
