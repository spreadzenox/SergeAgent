#!/usr/bin/env python3
"""Canon v2 schema: one SQLite authority, no FK constraints (loose links).

Tables follow D-spec layers: registres (state), épisodes (append-only),
tickets (H), leçons/playbooks/pitfalls (couche 3), summaries (couche 4),
usage metering (P2). Voice/SMS keep their bounded ledgers (migration
tracked separately); consents/blocklist here are the global store.
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 3

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS ventures (
    id TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '',
    lifecycle TEXT NOT NULL DEFAULT 'CANDIDATE',
    schedulable INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
    display TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
    regime TEXT NOT NULL DEFAULT 'OUTBOUND',
    funnel_state TEXT NOT NULL DEFAULT 'NEW',
    last_inbound_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS campaigns (
    id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
    family TEXT NOT NULL, channel TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'DRAFT',
    n_target INTEGER NOT NULL DEFAULT 0,
    budget_cap_eur REAL NOT NULL DEFAULT 0,
    window_start TEXT NOT NULL DEFAULT '',
    window_end TEXT NOT NULL DEFAULT '',
    thresholds_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS touches (
    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL,
    contact_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL, kind TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    cost_eur REAL NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_touches_campaign ON touches(campaign_id);
CREATE TABLE IF NOT EXISTS inbound_events (
    id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL, native_type TEXT NOT NULL,
    signal TEXT NOT NULL, class TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0,
    cost_eur REAL NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS consents (
    id TEXT PRIMARY KEY, channel TEXT NOT NULL,
    subject_hash TEXT NOT NULL, subject_ref TEXT NOT NULL DEFAULT '',
    basis TEXT NOT NULL, granted_at TEXT NOT NULL,
    revoked_at TEXT NOT NULL DEFAULT '',
    UNIQUE(channel, subject_hash));
CREATE TABLE IF NOT EXISTS blocklist (
    id TEXT PRIMARY KEY, channel TEXT NOT NULL,
    subject_hash TEXT NOT NULL, subject_ref TEXT NOT NULL DEFAULT '',
    reason TEXT NOT NULL, added_at TEXT NOT NULL,
    UNIQUE(channel, subject_hash));
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
    kind TEXT NOT NULL, amount_eur REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'EUR',
    intent_id TEXT NOT NULL UNIQUE,
    doc_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    receipt_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, actor TEXT NOT NULL,
    venture_id TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL, payload_json TEXT NOT NULL DEFAULT '{}',
    links_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS idx_events_ts_type ON events(ts, type);
CREATE TABLE IF NOT EXISTS work_items (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    venture_id TEXT NOT NULL DEFAULT '',
    campaign_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    ticket_id TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'READY',
    priority INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    blocked_until TEXT NOT NULL DEFAULT '',
    attempts INTEGER NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_work_ready
    ON work_items(status, blocked_until, priority DESC, created_at);
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY, type TEXT NOT NULL, title TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'DRAFT',
    payload_json TEXT NOT NULL DEFAULT '{}',
    expiry_at TEXT NOT NULL DEFAULT '',
    default_action TEXT NOT NULL DEFAULT '',
    versions_json TEXT NOT NULL DEFAULT '[]',
    thread_ref TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_tickets_state ON tickets(state, type);
CREATE TABLE IF NOT EXISTS ticket_items (
    id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL,
    kind TEXT NOT NULL, label TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    payload_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS ticket_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL, ts TEXT NOT NULL,
    actor TEXT NOT NULL, kind TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS lessons (
    id TEXT PRIMARY KEY, statement TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    scope TEXT NOT NULL DEFAULT 'global',
    status TEXT NOT NULL DEFAULT 'candidate',
    sources_json TEXT NOT NULL DEFAULT '[]',
    created_by TEXT NOT NULL DEFAULT '',
    confirm_count INTEGER NOT NULL DEFAULT 0,
    infirm_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS playbooks (
    id TEXT PRIMARY KEY, name TEXT NOT NULL,
    conditions TEXT NOT NULL DEFAULT '',
    steps_json TEXT NOT NULL DEFAULT '[]',
    scope TEXT NOT NULL DEFAULT 'global',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS pitfalls (
    id TEXT PRIMARY KEY, statement TEXT NOT NULL,
    cost_observed TEXT NOT NULL DEFAULT '',
    scope TEXT NOT NULL DEFAULT 'global',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS summaries (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    subject_id TEXT NOT NULL DEFAULT '',
    content TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    previous TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
    kind TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1,
    path_or_url TEXT NOT NULL, hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS subscriptions (
    id TEXT PRIMARY KEY, venture_id TEXT NOT NULL DEFAULT '',
    provider TEXT NOT NULL, external_id TEXT NOT NULL DEFAULT '',
    amount_eur REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'EUR',
    period TEXT NOT NULL DEFAULT 'monthly',
    status TEXT NOT NULL DEFAULT 'active',
    renews_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts_standing (
    id TEXT PRIMARY KEY, venue TEXT NOT NULL,
    handle TEXT NOT NULL, capital REAL NOT NULL DEFAULT 1.0,
    age_days INTEGER NOT NULL DEFAULT 0,
    warnings INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    cooldown_until TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    UNIQUE(venue, handle));
CREATE TABLE IF NOT EXISTS policy_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_hash TEXT NOT NULL, content_json TEXT NOT NULL,
    applied_by TEXT NOT NULL DEFAULT '',
    active_from TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS llm_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    point TEXT NOT NULL, tier TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    tokens_in INTEGER NOT NULL DEFAULT 0,
    tokens_out INTEGER NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    verdict TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS episode_archives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL, period TEXT NOT NULL DEFAULT '',
    count INTEGER NOT NULL DEFAULT 0, sha256 TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS listen_docs (
    id TEXT PRIMARY KEY, source TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
    excerpt TEXT NOT NULL DEFAULT '', published TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL, cluster_id TEXT NOT NULL DEFAULT '');
"""

TABLES = (
    'schema_version',
    'ventures',
    'contacts',
    'campaigns',
    'touches',
    'inbound_events',
    'consents',
    'blocklist',
    'transactions',
    'events',
    'work_items',
    'tickets',
    'ticket_items',
    'ticket_events',
    'lessons',
    'playbooks',
    'pitfalls',
    'summaries',
    'artifacts',
    'subscriptions',
    'accounts_standing',
    'policy_snapshots',
    'llm_usage',
    'episode_archives',
    'listen_docs',
)


def init_schema(connection: sqlite3.Connection) -> None:
    """Create all canon tables (idempotent) + stamp schema version.

    Args:
        connection: Open SQLite connection (committed by caller).
    """
    connection.executescript(SCHEMA_SQL)
    connection.execute('DELETE FROM schema_version')
    connection.execute(
        "INSERT INTO schema_version(version, applied_at) VALUES(?, datetime('now'))",
        (SCHEMA_VERSION,),
    )
