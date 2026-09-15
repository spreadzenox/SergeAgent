#!/usr/bin/env python3
"""Trace de contact par lieu : upsert, jamais de fusion entre canaux."""

from __future__ import annotations

import sqlite3

from serge.db.store import utcnow
from serge.funnels.contacts import create_contact


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
    """Crée ou enrichit la fiche de ce lieu. L’autre lieu reste une autre ligne.

    Args:
        conn: Canon (commit par l’appelant).
        venture_id: Venture.
        venue: Lieu (``linkedin``, ``reddit``, ``email``…).
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
    row = conn.execute(
        'SELECT id, display, email, phone, profile_url FROM contacts'
        ' WHERE venture_id=? AND venue=? AND handle=?',
        (venture_id, lieu, cle),
    ).fetchone()
    if row is None:
        ident = create_contact(
            conn,
            venture_id,
            display.strip() or cle,
            email=email.strip(),
            phone=phone.strip(),
        )
        conn.execute(
            'UPDATE contacts SET venue=?, handle=?, profile_url=? WHERE id=?',
            (lieu, cle, profile_url.strip(), ident),
        )
        return ident
    ident = str(row[0])
    conn.execute(
        'UPDATE contacts SET display=?, email=?, phone=?, profile_url=?,'
        ' updated_at=? WHERE id=?',
        (
            display.strip() or str(row[1] or cle),
            email.strip() or str(row[2] or ''),
            phone.strip() or str(row[3] or ''),
            profile_url.strip() or str(row[4] or ''),
            utcnow(),
            ident,
        ),
    )
    return ident
