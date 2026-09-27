#!/usr/bin/env python3
"""Migration v22 : une ligne par adresse de contact.

Les adresses d'un contact vivaient dans la colonne JSON
``contacts.contact_reference_by_canal`` (une adresse par canal). Elles
passent dans ``contact_addresses`` : une ligne par adresse. Le canal
``voice`` devient ``phone``. La colonne JSON est ensuite supprimée.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata


def _norm(channel: str, value: str) -> str:
    # Copie figée de ``serge.funnels.contacts.normalise_value``.
    text = unicodedata.normalize('NFKC', value).strip()
    if channel == 'email':
        return text.casefold()
    if channel == 'phone':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return f'+{digits}' if text.startswith('+') and digits else digits
    return text


def _adresses(channel: str, reference: dict) -> list[tuple[str, str]]:
    """``(canal, valeur)`` tirés d'une ancienne référence JSON."""
    found: list[tuple[str, str]] = []
    for field in ('address', 'phone', 'handle', 'profile_url'):
        value = reference.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        if field == 'address':
            found.append(('email', value.strip()))
        elif field == 'phone':
            found.append(('phone', value.strip()))
        else:
            found.append((channel, value.strip()))
    return found


def apply_v022(connection: sqlite3.Connection) -> None:
    """Range les adresses de contact dans ``contact_addresses``."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS contact_addresses (
            contact_id TEXT NOT NULL,
            channel TEXT NOT NULL,
            value TEXT NOT NULL,
            value_norm TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            PRIMARY KEY (contact_id, channel, value_norm)
        );
        CREATE INDEX IF NOT EXISTS idx_contact_addresses_value
            ON contact_addresses(channel, value_norm);
        """
    )
    colonnes = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(contacts)')
    }
    if 'contact_reference_by_canal' not in colonnes:
        return
    for ident, raw, created_at in connection.execute(
        'SELECT id, contact_reference_by_canal, created_at FROM contacts'
    ).fetchall():
        try:
            data = json.loads(raw or '{}')
        except (TypeError, ValueError):
            data = {}
        if not isinstance(data, dict):
            continue
        for channel, reference in data.items():
            if not isinstance(reference, dict):
                continue
            active = 0 if reference.get('active') is False else 1
            for canal, value in _adresses(str(channel), reference):
                norm = _norm(canal, value)
                if not norm:
                    continue
                connection.execute(
                    'INSERT OR IGNORE INTO contact_addresses(contact_id,'
                    ' channel, value, value_norm, active, created_at)'
                    ' VALUES(?,?,?,?,?,?)',
                    (ident, canal, value, norm, active, created_at),
                )
    connection.execute(
        'ALTER TABLE contacts DROP COLUMN contact_reference_by_canal'
    )
