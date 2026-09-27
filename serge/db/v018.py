#!/usr/bin/env python3
"""Migration v18 : références de contact regroupées par canal.

Le document stocké dans ``contacts.contact_reference_by_canal`` est une map
``canal -> référence``. Les canaux de sortie canoniques sont ``email``
(``address``) et ``voice`` (``phone``); une trace web conserve ``handle`` et
``profile_url`` sous sa clé de venue. Chaque référence porte ``active``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _references(row: sqlite3.Row) -> dict[str, dict[str, Any]]:
    try:
        parsed = json.loads(row['contact_reference_by_canal'] or '{}')
    except (TypeError, ValueError):
        parsed = {}
    result = (
        {
            str(channel): dict(reference)
            for channel, reference in parsed.items()
            if isinstance(channel, str) and isinstance(reference, dict)
        }
        if isinstance(parsed, dict)
        else {}
    )

    def reference(channel: str) -> dict[str, Any]:
        current = result.get(channel)
        if current is None:
            current = {}
            result[channel] = current
        current.setdefault('active', True)
        return current

    email = str(row['email'] or '').strip()
    if email:
        ref = reference('email')
        ref.setdefault('address', email)
    phone = str(row['phone'] or '').strip()
    if phone:
        ref = reference('voice')
        ref.setdefault('phone', phone)

    venue = str(row['venue'] or '').strip()
    handle = str(row['handle'] or '').strip()
    profile_url = str(row['profile_url'] or '').strip()
    if venue or handle or profile_url:
        channel = {
            'gmail': 'email',
            'mail': 'email',
            'phone': 'voice',
            'telephone': 'voice',
        }.get(
            venue,
            venue or ('email' if email else 'voice' if phone else 'other'),
        )
        ref = reference(channel)
        if venue:
            ref.setdefault('venue', venue)
        if handle:
            ref.setdefault('handle', handle)
        if profile_url:
            ref.setdefault('profile_url', profile_url)
        if channel == 'email' and handle:
            ref.setdefault('address', email or handle)
        if channel == 'voice' and handle:
            ref.setdefault('phone', phone or handle)

    return result


def apply_v018(connection: sqlite3.Connection) -> None:
    """Backfill then rebuild ``contacts`` without legacy reference columns."""
    columns = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(contacts)')
    }
    if 'contact_reference_by_canal' not in columns:
        connection.execute(
            'ALTER TABLE contacts ADD COLUMN contact_reference_by_canal'
            " TEXT NOT NULL DEFAULT '{}'"
        )
        columns.add('contact_reference_by_canal')

    legacy = {'email', 'phone', 'venue', 'handle', 'profile_url'} & columns
    if not legacy:
        return

    previous_factory = connection.row_factory
    connection.row_factory = sqlite3.Row
    try:
        legacy_select = ', '.join(
            field if field in columns else f"'' AS {field}"
            for field in ('email', 'phone', 'venue', 'handle', 'profile_url')
        )
        rows = connection.execute(
            'SELECT id, venture_id, display, contact_reference_by_canal,'
            f' {legacy_select}, regime, funnel_state, last_inbound_at,'
            ' created_at, updated_at FROM contacts'
        ).fetchall()
    finally:
        connection.row_factory = previous_factory
    prepared = [
        (
            row['id'],
            row['venture_id'],
            row['display'],
            json.dumps(_references(row), ensure_ascii=False, sort_keys=True),
            row['regime'],
            row['funnel_state'],
            row['last_inbound_at'],
            row['created_at'],
            row['updated_at'],
        )
        for row in rows
    ]

    connection.execute('DROP INDEX IF EXISTS idx_contacts_trace')
    connection.execute('ALTER TABLE contacts RENAME TO contacts_v017')
    connection.execute(
        """CREATE TABLE contacts (
            id TEXT PRIMARY KEY, venture_id TEXT NOT NULL,
            display TEXT NOT NULL DEFAULT '',
            contact_reference_by_canal TEXT NOT NULL DEFAULT '{}',
            regime TEXT NOT NULL DEFAULT 'OUTBOUND',
            funnel_state TEXT NOT NULL DEFAULT 'NEW',
            last_inbound_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL)
        """
    )
    connection.executemany(
        'INSERT INTO contacts(id, venture_id, display,'
        ' contact_reference_by_canal, regime, funnel_state, last_inbound_at,'
        ' created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?)',
        prepared,
    )
    connection.execute('DROP TABLE contacts_v017')
