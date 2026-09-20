#!/usr/bin/env python3
"""Références de contact par canal : upsert et déduplication canonique."""

from __future__ import annotations

import sqlite3

from serge.db.store import utcnow
from serge.funnels.contacts import (
    contact_references,
    find_contact_by_reference,
    insert_contact,
    set_contact_reference,
)


class ContactCanalError(ValueError):
    """Lieu ou identifiant de trace invalide."""


def upsert_trace(
    conn: sqlite3.Connection,
    venture_id: str,
    venue: str,
    handle: str,
    *,
    display: str = '',
    email: str = '',
    phone: str = '',
    profile_url: str = '',
) -> str:
    """Crée ou enrichit la référence de ce lieu.

    Args:
        conn: Canon (commit par l’appelant).
        venture_id: Venture.
        venue: Canal/lieu (``linkedin``, ``reddit``, ``email``…).
        handle: Identifiant sur ce lieu (pseudo, URL, adresse).
        display: Nom affiché, s’il est connu.
        email: Mail, seulement s’il vient de **ce** lieu.
        phone: Téléphone, seulement s’il vient de **ce** lieu.
        profile_url: URL de profil, si on l’a.

    Returns:
        Id du contact (créé ou déjà là).

    Raises:
        ContactCanalError: Lieu ou handle vide.
    """
    lieu = venue.strip()
    cle = handle.strip()
    if not lieu or not cle:
        raise ContactCanalError('lieu et identifiant requis')

    canal = {
        'gmail': 'email',
        'mail': 'email',
        'phone': 'voice',
        'telephone': 'voice',
    }.get(lieu, lieu)
    trace: dict[str, str | bool]
    if canal == 'email':
        trace = {'address': cle, 'handle': cle, 'venue': lieu}
    elif canal == 'voice':
        trace = {'phone': cle, 'handle': cle, 'venue': lieu}
    else:
        trace = {'handle': cle, 'venue': lieu}
    if profile_url.strip():
        trace['profile_url'] = profile_url.strip()

    ident = find_contact_by_reference(conn, venture_id, canal, trace)
    if ident is None and email.strip():
        ident = find_contact_by_reference(
            conn, venture_id, 'email', {'address': email.strip()}
        )
    if ident is None and phone.strip():
        ident = find_contact_by_reference(
            conn, venture_id, 'voice', {'phone': phone.strip()}
        )

    if ident is None:
        references: dict[str, dict[str, str | bool]] = {canal: trace}
        if email.strip():
            references['email'] = {
                'address': email.strip(),
                'active': True,
            }
        if phone.strip():
            references['voice'] = {'phone': phone.strip(), 'active': True}
        return insert_contact(
            conn,
            venture_id,
            display.strip() or cle,
            references,
        )

    references = contact_references(conn, ident)
    merged = dict(references.get(canal, {}))
    merged.update({key: value for key, value in trace.items() if value})
    merged['active'] = True
    set_contact_reference(conn, ident, canal, merged)
    if email.strip():
        current = dict(references.get('email', {}))
        current['address'] = email.strip()
        current['active'] = True
        set_contact_reference(conn, ident, 'email', current)
    if phone.strip():
        current = dict(references.get('voice', {}))
        current['phone'] = phone.strip()
        current['active'] = True
        set_contact_reference(conn, ident, 'voice', current)
    conn.execute(
        'UPDATE contacts SET display=?, updated_at=? WHERE id=?',
        (display.strip() or _display_for(conn, ident, cle), utcnow(), ident),
    )
    return ident


def _display_for(
    conn: sqlite3.Connection, contact_id: str, fallback: str
) -> str:
    row = conn.execute(
        'SELECT display FROM contacts WHERE id=?', (contact_id,)
    ).fetchone()
    return str(row[0] or fallback) if row else fallback
