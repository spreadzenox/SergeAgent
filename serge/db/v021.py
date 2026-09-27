#!/usr/bin/env python3
"""Migration v21 : un business = une seule ligne dans ``ventures``.

Les business trouvés par l'étape 1 vivaient dans ``business_candidates``
et leurs sélections dans ``poc_selections``. Ils passent dans ``ventures``
(statut ``CANDIDATE`` ou ``POC_SELECTED``) ; leurs pages de preuve passent
dans ``venture_sources``. Chaque ancienne sélection est recopiée dans le
journal, puis les trois anciennes tables sont supprimées.
"""

from __future__ import annotations

import json
import sqlite3

COLONNES = (
    ('description', "TEXT NOT NULL DEFAULT ''"),
    ('observations', "TEXT NOT NULL DEFAULT ''"),
    ('sellable_offer', "TEXT NOT NULL DEFAULT ''"),
    ('dedup_key', "TEXT NOT NULL DEFAULT ''"),
    ('smoke_started_at', "TEXT NOT NULL DEFAULT ''"),
    ('smoke_ended_at', "TEXT NOT NULL DEFAULT ''"),
)

# Tools de lecture qui lisaient les anciennes tables : leur catalogue est
# effacé ici et resemé au boot sur ``ventures``.
TOOLS_A_RESEMER = ('known_business_candidates', 'eligible_poc_candidates')


def _tables(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def apply_v021(connection: sqlite3.Connection) -> None:
    """Fond les business de l'étape 1 dans ``ventures``."""
    colonnes = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(ventures)')
    }
    for nom, definition in COLONNES:
        if nom not in colonnes:
            connection.execute(
                f'ALTER TABLE ventures ADD COLUMN {nom} {definition}'
            )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS venture_sources (
            venture_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            PRIMARY KEY (venture_id, doc_id, cycle_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ventures_dedup_key
            ON ventures(dedup_key) WHERE dedup_key <> '';
        """
    )
    tables = _tables(connection)
    if 'business_candidates' in tables:
        connection.execute(
            'INSERT OR IGNORE INTO ventures(id, name, lifecycle, schedulable,'
            ' description, observations, sellable_offer, dedup_key,'
            ' created_at, updated_at)'
            " SELECT id, title, CASE WHEN status='POC_SELECTED'"
            " THEN 'POC_SELECTED' ELSE 'CANDIDATE' END, 0, content,"
            ' observations, sellable_offer, normalized_key, created_at,'
            ' updated_at FROM business_candidates'
        )
    if 'business_candidate_sources' in tables:
        connection.execute(
            'INSERT OR IGNORE INTO venture_sources(venture_id, doc_id, cycle_id)'
            ' SELECT candidate_id, doc_id, cycle_id'
            ' FROM business_candidate_sources'
        )
    if 'poc_selections' in tables:
        for cycle_id, candidate_id, rank, selected_at in connection.execute(
            'SELECT cycle_id, candidate_id, rank, selected_at'
            ' FROM poc_selections'
        ).fetchall():
            connection.execute(
                'INSERT INTO events(ts, actor, venture_id, type, payload_json)'
                ' VALUES(?,?,?,?,?)',
                (
                    selected_at,
                    'migration.v021',
                    candidate_id,
                    'venture.poc_selected',
                    json.dumps({'cycle_id': cycle_id, 'rank': rank}),
                ),
            )
    for table in ('tool_db_tables', 'tool_db_columns', 'tool_db_filters'):
        if table in tables:
            connection.execute(
                f'DELETE FROM {table} WHERE tool_id IN (?, ?)',
                TOOLS_A_RESEMER,
            )
    connection.executescript(
        """
        DROP TABLE IF EXISTS poc_selections;
        DROP TABLE IF EXISTS business_candidate_sources;
        DROP TABLE IF EXISTS business_candidates;
        """
    )
