#!/usr/bin/env python3
"""Contacts : une fiche par personne, une ligne par adresse.

Une fiche ``contacts`` porte l'état de la personne dans un business
(NEW → QUALIFIED → CONTACTING → ENGAGED → INTENT → MEETING|CUSTOMER, ou une
branche d'arrêt). Ses adresses (e-mail, téléphone, profil sur un réseau)
sont dans ``contact_addresses`` : une ligne par adresse, jamais écrasée.

Règle de regroupement, dans un même business :

1. Une adresse déjà connue sur le même canal désigne la même personne.
   Exemple : ``ada@acme.fr`` puis ``ADA@acme.fr`` → une seule fiche.
2. Une adresse e-mail générique (``contact@``, ``info@``…) ne regroupe
   jamais : deux personnes peuvent écrire depuis la même boîte.
3. Rien d'autre ne regroupe : ni le nom, ni un même pseudo sur deux
   réseaux différents.
"""

from __future__ import annotations

import sqlite3
import unicodedata
import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from serge.db.store import utcnow
from serge.funnels.contact_errors import ContactError

# Début d'adresse e-mail partagé par plusieurs personnes : pas de
# regroupement automatique sur ces adresses.
EMAILS_GENERIQUES = frozenset(
    {
        'accueil',
        'admin',
        'bonjour',
        'commercial',
        'contact',
        'hello',
        'help',
        'info',
        'infos',
        'jobs',
        'mail',
        'marketing',
        'no-reply',
        'noreply',
        'office',
        'rh',
        'sales',
        'service',
        'support',
        'team',
        'webmaster',
    }
)


def _new_id() -> str:
    return f'p_{uuid.uuid4().hex[:12]}'


def normalise_value(channel: str, value: str) -> str:
    """Forme comparable d'une adresse.

    E-mail : sans majuscules. Téléphone : le ``+`` de tête et les chiffres.
    Autre canal : le texte tel quel (un pseudo distingue les majuscules).
    """
    text = unicodedata.normalize('NFKC', str(value or '')).strip()
    if channel == 'email':
        return text.casefold()
    if channel == 'phone':
        digits = ''.join(ch for ch in text if ch.isdigit())
        return f'+{digits}' if text.startswith('+') and digits else digits
    return text


def is_generic_email(value: str) -> bool:
    """Vrai pour une boîte partagée comme ``contact@acme.fr``."""
    local = normalise_value('email', value).partition('@')[0]
    return local in EMAILS_GENERIQUES


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


def find_contact(
    conn: sqlite3.Connection, venture_id: str, channel: str, value: str
) -> str | None:
    """La fiche qui porte cette adresse. ``venture_id`` vide : tous."""
    norm = normalise_value(channel, value)
    if not norm:
        return None
    sql = (
        'SELECT a.contact_id FROM contact_addresses a'
        ' JOIN contacts c ON c.id=a.contact_id'
        ' WHERE a.channel=? AND a.value_norm=?'
    )
    params: list[str] = [channel, norm]
    if venture_id:
        sql += ' AND c.venture_id=?'
        params.append(venture_id)
    row = conn.execute(
        sql + ' ORDER BY c.created_at LIMIT 1', params
    ).fetchone()
    return str(row[0]) if row else None


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


def upsert_contact(
    conn: sqlite3.Connection,
    venture_id: str,
    display: str,
    addresses_in: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Crée une fiche, ou ajoute des adresses à la fiche déjà connue.

    Si les adresses désignent deux fiches différentes, rien n'est écrit :
    Serge ne fusionne jamais deux personnes tout seul.
    """
    venture = str(venture_id or '').strip()
    name = str(display or '').strip()
    if not venture:
        raise ContactError('venture_id requis')
    if not name:
        raise ContactError('display requis')
    rows = [_clean(raw) for raw in addresses_in]
    if not rows:
        raise ContactError('au moins une adresse est requise')

    matched: dict[str, list[dict[str, str]]] = {}
    for channel, value, _active in rows:
        if channel == 'email' and is_generic_email(value):
            continue
        ident = find_contact(conn, venture, channel, value)
        if ident:
            matched.setdefault(ident, []).append(
                {'channel': channel, 'value': value}
            )
    if len(matched) > 1:
        return {
            'ok': False,
            'code': 'duplicate',
            'matched_contact_ids': sorted(matched),
            'matched': [
                {'contact_id': ident, **item}
                for ident in sorted(matched)
                for item in matched[ident]
            ],
        }

    if not matched:
        ident = create_contact(
            conn,
            venture,
            name,
            [{'channel': c, 'value': v, 'active': a} for c, v, a in rows],
        )
        return {
            'ok': True,
            'created': True,
            'contact_id': ident,
            'added': [{'channel': c, 'value': v} for c, v, _a in rows],
        }

    ident = next(iter(matched))
    added = [
        {'channel': channel, 'value': value}
        for channel, value, active in rows
        if add_address(conn, ident, channel, value, active=active)
    ]
    conn.execute(
        "UPDATE contacts SET display=CASE WHEN display='' THEN ? ELSE display"
        ' END, updated_at=? WHERE id=?',
        (name, utcnow(), ident),
    )
    return {
        'ok': True,
        'created': False,
        'contact_id': ident,
        'added': added,
        'matched': matched[ident],
    }


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
