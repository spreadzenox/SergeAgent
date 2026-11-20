#!/usr/bin/env python3
"""Contacts : une fiche par personne, une ligne par adresse.

Une fiche ``contacts`` porte l'état de la personne dans un business
(NEW → QUALIFIED → CONTACTING → ENGAGED → INTENT → MEETING|CUSTOMER, ou une
branche d'arrêt). Ses adresses (e-mail, téléphone, profil sur un réseau)
sont dans ``contact_addresses`` : une ligne par adresse, jamais écrasée.

Une adresse se compare sous sa forme normale (``normalise_value``) :
``ada@acme.fr`` et ``ADA@acme.fr`` sont la même. Les adresses génériques
(``contact@``, ``info@``…) sont refusées par « Ajouter un prospect »
(``serge/campaigns/prospect.py``), d'après un réglage de la page Policy.
"""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from serge.db.store import utcnow
from serge.funnels.contact_errors import ContactError


def _new_id() -> str:
    return f'p_{uuid.uuid4().hex[:12]}'


def normalise_value(channel: str, value: str) -> str:
    """Forme comparable d'une adresse.

    E-mail : sans majuscules. Téléphone : le ``+`` de tête et les chiffres.
    L'adresse d'un profil sur un site : sans ``https://``, ``www.``, ce qui
    suit un ``?`` ou un ``#``, la barre de fin ni les majuscules (exemple :
    ``https://www.linkedin.com/in/Ana-Roux/?x=1`` et
    ``linkedin.com/in/ana-roux`` sont la même personne). Autre : le texte
    tel quel (un pseudo distingue les majuscules).
    """
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    if channel == 'email':
        return text.casefold()
    if channel == 'phone':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return f'+{digits}' if text.startswith('+') and digits else digits
    if text.casefold().startswith(('http://', 'https://')):
        sans = text.split('://', 1)[1].split('?', 1)[0].split('#', 1)[0]
        return sans.casefold().removeprefix('www.').rstrip('/')
    return text


def _clean(raw: Mapping[str, Any]) -> tuple[str, str, bool]:
    channel = str(raw.get('channel') or '').strip()
    value = str(raw.get('value') or '').strip()
    if not channel:
        raise ContactError('canal requis')
    if not value or not normalise_value(channel, value):
        raise ContactError(f'adresse vide pour {channel}')
    active = raw.get('active', True)
    if not isinstance(active, bool):
        raise ContactError('active doit être vrai ou faux')
    return channel, value, active


def add_address(
    conn: sqlite3.Connection,
    contact_id: str,
    channel: str,
    value: str,
    *,
    active: bool = True,
) -> bool:
    """Ajoute une adresse à une fiche. Faux si elle y était déjà."""
    if (
        conn.execute(
            'SELECT 1 FROM contacts WHERE id=?', (contact_id,)
        ).fetchone()
        is None
    ):
        raise ContactError(f'contact inconnu : {contact_id}')
    channel, value, active = _clean(
        {'channel': channel, 'value': value, 'active': active}
    )
    cursor = conn.execute(
        'INSERT OR IGNORE INTO contact_addresses(contact_id, channel, value,'
        ' value_norm, active, created_at) VALUES(?,?,?,?,?,?)',
        (
            contact_id,
            channel,
            value,
            normalise_value(channel, value),
            int(active),
            utcnow(),
        ),
    )
    return cursor.rowcount > 0


def addresses(
    conn: sqlite3.Connection, contact_id: str
) -> list[dict[str, Any]]:
    """Toutes les adresses d'une fiche, les plus anciennes d'abord."""
    return [
        {'channel': row[0], 'value': row[1], 'active': bool(row[2])}
        for row in conn.execute(
            'SELECT channel, value, active FROM contact_addresses'
            ' WHERE contact_id=? ORDER BY created_at, rowid',
            (contact_id,),
        ).fetchall()
    ]


def address_value(
    conn: sqlite3.Connection, contact_id: str, channel: str
) -> str:
    """La plus ancienne adresse active de ce canal, ou ``''``."""
    row = conn.execute(
        'SELECT value FROM contact_addresses'
        ' WHERE contact_id=? AND channel=? AND active=1'
        ' ORDER BY created_at, rowid LIMIT 1',
        (contact_id, channel),
    ).fetchone()
    return str(row[0]) if row else ''


def create_contact(
    conn: sqlite3.Connection,
    venture_id: str,
    display: str,
    addresses_in: Iterable[Mapping[str, Any]] = (),
    *,
    email: str = '',
    phone: str = '',
) -> str:
    """Crée une fiche NEW OUTBOUND avec ses adresses."""
    rows = [_clean(raw) for raw in addresses_in]
    if email.strip():
        rows.append(('email', email.strip(), True))
    if phone.strip():
        rows.append(('phone', phone.strip(), True))
    contact_id = _new_id()
    moment = utcnow()
    conn.execute(
        'INSERT INTO contacts(id, venture_id, display, regime, funnel_state,'
        ' created_at, updated_at) VALUES(?,?,?,?,?,?,?)',
        (contact_id, venture_id, display, 'OUTBOUND', 'NEW', moment, moment),
    )
    for channel, value, active in rows:
        add_address(conn, contact_id, channel, value, active=active)
    return contact_id


from serge.funnels.contact_lifecycle import (  # noqa: E402,F401
    mark_blocked,
    mark_engaged,
    mark_intent,
    mark_invalid,
    mark_unreachable,
    note_inbound,
    opt_out,
    qualify,
    refresh_regime,
    reject,
    start_contacting,
    to_customer,
    to_meeting,
)
