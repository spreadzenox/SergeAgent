#!/usr/bin/env python3
"""Migration v24 : les tables du pipeline décrit en base (lot 6).

Le code devient un interpréteur de la base : chaque invocation, ce qu'elle
reçoit, ce qu'elle rend, où elle l'écrit, avec quelles protections, et ce
qui la lance sont des lignes de ces tables. Conception détaillée :
``docs/LOT6_CONCEPTION.md``.

Cette migration ne fait qu'ajouter. Les anciennes tables (``llm_points``,
``work_items``…) sont retirées plus tard, quand l'interpréteur les
remplace.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS capabilities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    doc_md TEXT NOT NULL DEFAULT '',
    available INTEGER NOT NULL DEFAULT 1 CHECK (available IN (0, 1)),
    code_path TEXT NOT NULL DEFAULT '',
    code_sha TEXT NOT NULL DEFAULT '',
    files_sha TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS capability_params (
    capability_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'text'
        CHECK (type IN ('text', 'number', 'bool', 'list')),
    required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (capability_id, name)
);
CREATE TABLE IF NOT EXISTS invocations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT '',
    step_id TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL CHECK (type IN ('llm', 'capability')),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    queue_id TEXT NOT NULL DEFAULT 'works',
    priority INTEGER NOT NULL DEFAULT 10
        CHECK (priority BETWEEN 0 AND 100),
    model_tier TEXT NOT NULL DEFAULT ''
        CHECK (model_tier IN ('', 'fast', 'mid', 'smart')),
    prompt TEXT NOT NULL DEFAULT '',
    gets_serge_intro INTEGER NOT NULL DEFAULT 0
        CHECK (gets_serge_intro IN (0, 1)),
    default_max_rows INTEGER NOT NULL DEFAULT 50,
    max_tool_turns INTEGER NOT NULL DEFAULT 12,
    capability_id TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT 'code' CHECK (origin IN ('code', 'mc')),
    deleted_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS invocation_tools (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invocation_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('given', 'callable')),
    label TEXT NOT NULL DEFAULT '',
    max_rows INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_invocation_tools_invocation
    ON invocation_tools(invocation_id, position);
CREATE TABLE IF NOT EXISTS invocation_tool_params (
    invocation_id TEXT NOT NULL,
    invocation_tool_id INTEGER NOT NULL DEFAULT 0,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('fixed', 'task')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (invocation_id, invocation_tool_id, param_name)
);
CREATE TABLE IF NOT EXISTS invocation_output_fields (
    invocation_id TEXT NOT NULL,
    path TEXT NOT NULL,
    type TEXT NOT NULL
        CHECK (type IN ('text', 'number', 'bool', 'list', 'choice')),
    choices TEXT NOT NULL DEFAULT '',
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (invocation_id, path)
);
CREATE TABLE IF NOT EXISTS writable_tables (
    table_name TEXT PRIMARY KEY,
    can_insert INTEGER NOT NULL DEFAULT 0 CHECK (can_insert IN (0, 1)),
    can_update INTEGER NOT NULL DEFAULT 0 CHECK (can_update IN (0, 1)),
    description TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS writable_columns (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (table_name, column_name)
);
CREATE TABLE IF NOT EXISTS invocation_writes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invocation_id TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    table_name TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('insert', 'update')),
    for_each TEXT NOT NULL DEFAULT '',
    parent_write_id INTEGER NOT NULL DEFAULT 0,
    key_column TEXT NOT NULL DEFAULT '',
    key_source TEXT NOT NULL DEFAULT ''
        CHECK (key_source IN ('', 'field', 'fixed', 'task')),
    key_value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_invocation_writes_invocation
    ON invocation_writes(invocation_id, position);
CREATE TABLE IF NOT EXISTS invocation_write_values (
    write_id INTEGER NOT NULL,
    column_name TEXT NOT NULL,
    source TEXT NOT NULL
        CHECK (source IN ('field', 'fixed', 'task', 'parent_row', 'now')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (write_id, column_name)
);
CREATE TABLE IF NOT EXISTS status_transitions (
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    from_value TEXT NOT NULL,
    to_value TEXT NOT NULL,
    PRIMARY KEY (table_name, column_name, from_value, to_value)
);
CREATE TABLE IF NOT EXISTS dedup_rules (
    id TEXT PRIMARY KEY,
    table_name TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('exact', 'shared_words')),
    threshold INTEGER NOT NULL DEFAULT 100
        CHECK (threshold BETWEEN 1 AND 100),
    on_duplicate TEXT NOT NULL DEFAULT 'skip'
        CHECK (on_duplicate IN ('skip', 'refuse'))
);
CREATE TABLE IF NOT EXISTS dedup_rule_columns (
    rule_id TEXT NOT NULL,
    column_name TEXT NOT NULL,
    PRIMARY KEY (rule_id, column_name)
);
CREATE TABLE IF NOT EXISTS links (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    from_invocation_id TEXT NOT NULL,
    to_invocation_id TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('on_finish', 'per_row')),
    write_id INTEGER NOT NULL DEFAULT 0,
    auto INTEGER NOT NULL DEFAULT 1 CHECK (auto IN (0, 1)),
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    origin TEXT NOT NULL DEFAULT 'code' CHECK (origin IN ('code', 'mc')),
    deleted_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS link_params (
    link_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('row', 'task', 'fixed')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (link_id, param_name)
);
CREATE TABLE IF NOT EXISTS link_passages (
    link_id TEXT NOT NULL,
    source_ref TEXT NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    passed_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (link_id, source_ref)
);
CREATE TABLE IF NOT EXISTS triggers (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    invocation_id TEXT NOT NULL,
    event TEXT NOT NULL
        CHECK (event IN ('row_written', 'every', 'at', 'button')),
    table_name TEXT NOT NULL DEFAULT '',
    filter_column TEXT NOT NULL DEFAULT '',
    filter_value TEXT NOT NULL DEFAULT '',
    every_minutes INTEGER NOT NULL DEFAULT 0,
    at_time TEXT NOT NULL DEFAULT '',
    at_days TEXT NOT NULL DEFAULT '',
    last_fired_at TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    origin TEXT NOT NULL DEFAULT 'code' CHECK (origin IN ('code', 'mc')),
    deleted_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT '',
    updated_by TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS trigger_params (
    trigger_id TEXT NOT NULL,
    param_name TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('row', 'form', 'fixed')),
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (trigger_id, param_name)
);
CREATE TABLE IF NOT EXISTS queues (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1))
);
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL,
    queue_id TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ready'
        CHECK (status IN ('ready', 'running', 'done', 'failed',
                          'cancelled')),
    not_before TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    origin TEXT NOT NULL DEFAULT ''
        CHECK (origin IN ('', 'link', 'trigger', 'button')),
    origin_ref TEXT NOT NULL DEFAULT '',
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT '',
    finished_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_tasks_ready
    ON tasks(queue_id, status, priority, created_at);
CREATE TABLE IF NOT EXISTS task_params (
    task_id TEXT NOT NULL,
    name TEXT NOT NULL,
    value TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (task_id, name)
);
CREATE TABLE IF NOT EXISTS task_inputs (
    task_id TEXT NOT NULL,
    invocation_tool_id INTEGER NOT NULL,
    rows_given INTEGER NOT NULL DEFAULT 0,
    rows_left_out INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (task_id, invocation_tool_id)
);
CREATE TABLE IF NOT EXISTS llm_models (
    tier TEXT PRIMARY KEY CHECK (tier IN ('fast', 'mid', 'smart')),
    provider TEXT NOT NULL DEFAULT '',
    model TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS serge_texts (
    id TEXT PRIMARY KEY,
    body TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
"""


def apply_v024(connection: sqlite3.Connection) -> None:
    """Crée les tables du pipeline décrit en base."""
    connection.executescript(SCRIPT)
    colonnes = {
        str(row[1]) for row in connection.execute('PRAGMA table_info(tools)')
    }
    if colonnes and 'capability_id' not in colonnes:
        connection.execute(
            'ALTER TABLE tools ADD COLUMN capability_id TEXT NOT NULL'
            " DEFAULT ''"
        )
