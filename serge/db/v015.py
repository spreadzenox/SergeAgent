#!/usr/bin/env python3
"""Migration v15 : cycles d'écoute, candidats et permissions de lecture."""

from __future__ import annotations

import sqlite3


def apply_v015(connection: sqlite3.Connection) -> None:
    """Ajoute le stockage canonique de l'écoute et des lecteurs DB."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS db_readers (
            id TEXT PRIMARY KEY,
            titre TEXT NOT NULL,
            doc_md TEXT NOT NULL DEFAULT '',
            code_path TEXT NOT NULL DEFAULT '',
            code_sha TEXT NOT NULL DEFAULT '',
            etat TEXT NOT NULL DEFAULT 'branche'
        );
        CREATE TABLE IF NOT EXISTS llm_point_readers (
            point_id TEXT NOT NULL,
            reader_id TEXT NOT NULL,
            usage TEXT NOT NULL DEFAULT 'autorise',
            enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL DEFAULT '',
            updated_by TEXT NOT NULL DEFAULT 'boot',
            PRIMARY KEY (point_id, reader_id)
        );
        CREATE TABLE IF NOT EXISTS listen_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            n_target INTEGER NOT NULL DEFAULT 5,
            p_target INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT NOT NULL,
            updated_by TEXT NOT NULL DEFAULT 'boot'
        );
        CREATE TABLE IF NOT EXISTS listen_cycles (
            id TEXT PRIMARY KEY,
            guide TEXT NOT NULL DEFAULT '',
            n_target INTEGER NOT NULL,
            p_target INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'READY',
            created_at TEXT NOT NULL,
            started_at TEXT NOT NULL DEFAULT '',
            finished_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS listen_cycle_docs (
            cycle_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            PRIMARY KEY (cycle_id, doc_id)
        );
        CREATE TABLE IF NOT EXISTS business_candidates (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            observations TEXT NOT NULL DEFAULT '',
            sellable_offer TEXT NOT NULL DEFAULT '',
            normalized_key TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'CANDIDATE',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS business_candidate_sources (
            candidate_id TEXT NOT NULL,
            doc_id TEXT NOT NULL,
            cycle_id TEXT NOT NULL,
            PRIMARY KEY (candidate_id, doc_id, cycle_id)
        );
        CREATE TABLE IF NOT EXISTS poc_selections (
            id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL,
            candidate_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'SELECTED',
            selected_at TEXT NOT NULL,
            UNIQUE (cycle_id, candidate_id)
        );
        CREATE INDEX IF NOT EXISTS idx_listen_cycle_docs_doc
            ON listen_cycle_docs(doc_id);
        CREATE INDEX IF NOT EXISTS idx_business_candidates_status
            ON business_candidates(status);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_poc_active_candidate
            ON poc_selections(candidate_id)
            WHERE status IN ('SELECTED', 'STARTED');
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO listen_settings"
        "(id, n_target, p_target, updated_at)"
        "VALUES(1, 5, 1, datetime('now'))"
    )