#!/usr/bin/env python3
"""Migration v39 : une réponse à un ticket réveille le pipeline (lot 8 bis).

Décisions Q85 et Q86 :

- ``tickets`` : ce dont parle le ticket (``ref_table``, ``ref_id`` : par
  exemple l'envoi qui attend), son business, son contact, et la question
  précise posée aux administrateurs.
- ``ticket_answers`` : chaque réponse à un ticket, une ligne : le bouton
  (``acte``), le texte saisi, qui a répondu ; et, recopiés du ticket, ce
  dont il parle. Une expiration y écrit aussi sa décision par défaut. Les
  déclencheurs « une ligne est écrite » de cette table réveillent les
  invocations réglées en base, par bouton.
- ``touches`` : ``needs_owner``, pourquoi l'invocation qui a écrit l'envoi
  demande un humain (vide : elle n'en a pas besoin) ; ``owner_question``,
  la question du contact sur le produit à laquelle la fiche ne répond
  pas ; ``owner_ok_at``, quand un humain l'a validé.
- ``ventures.validate_drafts`` : 1 si chaque brouillon de ce business
  attend la validation d'un humain avant de partir.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS ticket_answers (
    id TEXT PRIMARY KEY,
    ticket_id TEXT NOT NULL,
    ticket_type TEXT NOT NULL DEFAULT '',
    acte TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    answered_by TEXT NOT NULL DEFAULT '',
    ref_table TEXT NOT NULL DEFAULT '',
    ref_id TEXT NOT NULL DEFAULT '',
    venture_id TEXT NOT NULL DEFAULT '',
    contact_id TEXT NOT NULL DEFAULT '',
    question TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticket_answers_ticket
    ON ticket_answers(ticket_id);
"""

COLONNES = (
    ('tickets', 'ref_table', "TEXT NOT NULL DEFAULT ''"),
    ('tickets', 'ref_id', "TEXT NOT NULL DEFAULT ''"),
    ('tickets', 'venture_id', "TEXT NOT NULL DEFAULT ''"),
    ('tickets', 'contact_id', "TEXT NOT NULL DEFAULT ''"),
    ('tickets', 'question', "TEXT NOT NULL DEFAULT ''"),
    ('touches', 'needs_owner', "TEXT NOT NULL DEFAULT ''"),
    ('touches', 'owner_question', "TEXT NOT NULL DEFAULT ''"),
    ('touches', 'owner_ok_at', "TEXT NOT NULL DEFAULT ''"),
    ('ventures', 'validate_drafts', 'INTEGER NOT NULL DEFAULT 0'),
)


def apply_v039(connection: sqlite3.Connection) -> None:
    """Ajoute les réponses aux tickets et l'attente d'un humain."""
    connection.executescript(SCRIPT)
    for table, colonne, sorte in COLONNES:
        existantes = {
            str(r[1])
            for r in connection.execute(f'PRAGMA table_info({table})')
        }
        if colonne not in existantes:
            connection.execute(
                f'ALTER TABLE {table} ADD COLUMN {colonne} {sorte}'
            )
