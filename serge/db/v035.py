#!/usr/bin/env python3
"""Migration v35 : les canaux de conversation (lot 8, décision Q79).

Conception : ``docs/LOT8_CONCEPTION.md``.

- ``canaux`` : la sorte d'adresse d'un canal (``address_channel``), s'il est
  branché dans le code (``connected``), s'il se relève (``polls``) et sa
  dernière relève (``polled_at``).
- ``touches`` (ce que Serge envoie) et ``inbound_events`` (ce qu'il reçoit)
  gardent le texte des messages et de quoi les rattacher à un fil : ce sont
  les deux moitiés du fil d'un contact (décision Q37). Les deux tables sont
  refaites : une réponse n'appartient à aucune campagne, et un message reçu
  n'a plus de signal deviné par le code (``campaign_id`` et ``signal``
  deviennent facultatifs).
- Le pipeline en base apprend une condition sur un lien ou une écriture,
  un délai sur un lien, « une seule tâche en attente par contact », et les
  capacités qui agissent hors de Serge.
- Trois tables : la fiche produit, ses questions fréquentes, et les
  demandes des contacts sur le produit.
"""

from __future__ import annotations

import sqlite3

TEXT = "TEXT NOT NULL DEFAULT ''"

COLUMNS: dict[str, tuple[tuple[str, str], ...]] = {
    'canaux': (
        ('address_channel', TEXT),
        ('connected', 'INTEGER NOT NULL DEFAULT 0'),
        ('polls', 'INTEGER NOT NULL DEFAULT 0'),
        ('polled_at', TEXT),
    ),
    'links': (
        ('condition_field', TEXT),
        ('condition_op', TEXT),
        ('condition_value', TEXT),
        ('delay_min_setting', TEXT),
        ('delay_max_setting', TEXT),
    ),
    'invocation_writes': (
        ('condition_field', TEXT),
        ('condition_op', TEXT),
        ('condition_value', TEXT),
    ),
    'invocations': (('single_pending_param', TEXT),),
    'capabilities': (('acts_outside', 'INTEGER NOT NULL DEFAULT 0'),),
}

# Les deux moitiés du fil, refaites avec leurs nouvelles colonnes.
REBUILT: dict[str, str] = {
    'touches': """CREATE TABLE touches (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    venture_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    address TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'queued',
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    reply_to TEXT NOT NULL DEFAULT '',
    followup_of TEXT NOT NULL DEFAULT '',
    external_ref TEXT NOT NULL DEFAULT '',
    sent_at TEXT NOT NULL DEFAULT '',
    last_error TEXT NOT NULL DEFAULT '',
    cost_eur REAL NOT NULL DEFAULT 0,
    idempotency_key TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL)""",
    'inbound_events': """CREATE TABLE inbound_events (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    venture_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL,
    native_type TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    subject TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT '',
    message_ref TEXT NOT NULL DEFAULT '',
    external_ref TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT '',
    reaction TEXT NOT NULL DEFAULT '',
    signal TEXT NOT NULL DEFAULT '',
    class TEXT NOT NULL DEFAULT '',
    score REAL NOT NULL DEFAULT 0,
    cost_eur REAL NOT NULL DEFAULT 0,
    received_at TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}')""",
}

SCRIPT = """
CREATE INDEX IF NOT EXISTS idx_touches_campaign ON touches(campaign_id);
CREATE INDEX IF NOT EXISTS idx_touches_contact ON touches(contact_id);
CREATE INDEX IF NOT EXISTS idx_inbound_contact ON inbound_events(contact_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_inbound_external
    ON inbound_events(channel, external_ref) WHERE external_ref <> '';
CREATE TABLE IF NOT EXISTS product_sheets (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL DEFAULT '',
    limits TEXT NOT NULL DEFAULT '',
    price TEXT NOT NULL DEFAULT '',
    delays TEXT NOT NULL DEFAULT '',
    usage TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS product_faq (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS customer_requests (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    inbound_id TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL CHECK (kind IN ('bug', 'insatisfaction', 'idée')),
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [
        str(r[1]) for r in connection.execute(f'PRAGMA table_info({table})')
    ]


def _rebuild(connection: sqlite3.Connection, table: str, create: str) -> None:
    """Refait une table en gardant ses lignes (colonnes communes)."""
    old = set(_columns(connection, table))
    connection.execute(f'ALTER TABLE {table} RENAME TO {table}_v034')
    connection.execute(create)
    common = ', '.join(c for c in _columns(connection, table) if c in old)
    connection.execute(
        f'INSERT INTO {table}({common}) SELECT {common} FROM {table}_v034'
    )
    # Supprimer l'ancienne table supprime aussi ses index : le script les
    # recrée sur la nouvelle.
    connection.execute(f'DROP TABLE {table}_v034')


def apply_v035(connection: sqlite3.Connection) -> None:
    """Ajoute les colonnes et les tables des canaux de conversation."""
    for table, columns in COLUMNS.items():
        have = set(_columns(connection, table))
        for column, sql in columns:
            if column not in have:
                connection.execute(
                    f'ALTER TABLE {table} ADD COLUMN {column} {sql}'
                )
    for table, create in REBUILT.items():
        _rebuild(connection, table, create)
    connection.executescript(SCRIPT)
