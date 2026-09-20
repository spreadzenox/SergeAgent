#!/usr/bin/env python3
"""Contacts nommés : états §2.3 + régimes OUTBOUND/INBOUND §2.1.

NEW → QUALIFIED → CONTACTING → ENGAGED → INTENT → MEETING|CUSTOMER.
Branches : REJECTED, UNREACHABLE, OPTED_OUT/BLOCKED, INVALID (hors N).
INBOUND au 1er signal entrant, retour OUTBOUND après silence (policy).
Machine à états seule : le routeur orchestre (blocklist, files).
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import utcnow
from serge.funnels.contact_errors import ContactError

# Format canonique : {canal: {champs propres au canal, active: bool}}.
# ``email`` porte ``address``, ``voice`` porte ``phone``. Les canaux de trace
# web portent ``handle`` et, si connu, ``profile_url`` sous leur id de venue.
CONTACT_REFERENCE_COLUMN = 'contact_reference_by_canal'


def _new_id() -> str:
    return f'p_{uuid.uuid4().hex[:12]}'


def load_contact_references(raw: Any) -> dict[str, dict[str, Any]]:
    """Décode la map JSON des références, en ignorant les formes invalides."""
    if isinstance(raw, str):
        try:
            data = json.loads(raw or '{}')
        except (TypeError, ValueError):
            data = {}
    elif isinstance(raw, Mapping):
        data = raw
    else:
        data = {}
    if not isinstance(data, Mapping):
        return {}
    return {
        str(channel): dict(reference)
        for channel, reference in data.items()
        if isinstance(channel, str) and isinstance(reference, Mapping)
    }


def _references_from_row(row: Any) -> dict[str, dict[str, Any]]:
    if isinstance(row, str):
        return load_contact_references(row)
    if isinstance(row, Mapping):
        if CONTACT_REFERENCE_COLUMN in row:
            return load_contact_references(row[CONTACT_REFERENCE_COLUMN])
        return load_contact_references(row)
    try:
        return load_contact_references(row[CONTACT_REFERENCE_COLUMN])
    except (IndexError, KeyError, TypeError):
        try:
            for value in row:
                if isinstance(value, str):
                    references = load_contact_references(value)
                    if references:
                        return references
        except TypeError:
            pass
        return {}


def contact_reference(row: Any, channel: str) -> dict[str, Any]:
    """Retourne une référence de canal depuis une ligne ou une map JSON."""
    return dict(_references_from_row(row).get(channel, {}))


def contact_reference_value(
    row: Any, channel: str, field: str | None = None
) -> str:
    """Retourne la valeur adressable d’une référence de canal."""
    reference = contact_reference(row, channel)
    return _reference_value(reference, channel, field)


def contact_reference_active(row: Any, channel: str) -> bool:
    """Indique si une référence existe et autorise le runtime du canal."""
    reference = contact_reference(row, channel)
    return bool(reference) and bool(reference.get('active', True))


def _reference_value(
    reference: Mapping[str, Any], channel: str, field: str | None = None
) -> str:
    if field:
        return str(reference.get(field) or '')
    key = {'email': 'address', 'voice': 'phone'}.get(channel, 'handle')
    return str(
        reference.get(key)
        or reference.get('address')
        or reference.get('phone')
        or reference.get('profile_url')
        or ''
    )


def _normalise_reference(channel: str, raw: Any) -> dict[str, Any]:
    canal = str(channel).strip()
    if not canal:
        raise ContactError('canal requis')
    if isinstance(raw, Mapping):
        reference = dict(raw)
    elif isinstance(raw, str):
        reference = {}
        value = raw.strip()
        if canal == 'email':
            reference['address'] = value
        elif canal == 'voice':
            reference['phone'] = value
        else:
            reference['handle'] = value
    else:
        raise ContactError(f'référence invalide pour {canal}')
    for key in ('address', 'phone', 'handle', 'profile_url', 'venue'):
        if key in reference and isinstance(reference[key], str):
            reference[key] = reference[key].strip()
    if canal == 'email' and not reference.get('address'):
        if reference.get('handle'):
            reference['address'] = reference['handle']
    if canal == 'voice' and not reference.get('phone'):
        if reference.get('handle'):
            reference['phone'] = reference['handle']
    reference['active'] = bool(reference.get('active', True))
    return reference


def normalise_contact_references(raw: Any) -> dict[str, dict[str, Any]]:
    """Normalise une map de canaux ou une référence structurée unique.

    La forme unique acceptée est ``{'channel': 'email', 'address': ...}``
    (``canal`` est aussi accepté); la forme canonique est une map indexée par
    canal.
    """
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        raise ContactError('références de canal invalides')
    if 'contact_reference_by_canal' in raw:
        raw = raw['contact_reference_by_canal']
    if not isinstance(raw, Mapping):
        raise ContactError('références de canal invalides')
    channel = raw.get('channel') or raw.get('canal')
    if channel:
        payload = {
            key: value
            for key, value in raw.items()
            if key not in {'channel', 'canal'}
        }
        return {str(channel): _normalise_reference(str(channel), payload)}
    return {
        str(channel): _normalise_reference(str(channel), reference)
        for channel, reference in raw.items()
    }


def _dump_references(references: Mapping[str, Mapping[str, Any]]) -> str:
    return json.dumps(references, ensure_ascii=False, sort_keys=True)


def set_contact_reference(
    conn: sqlite3.Connection,
    contact_id: str,
    channel: str,
    reference: Mapping[str, Any] | str,
) -> None:
    """Ajoute/remplace une référence sans toucher à l’état funnel."""
    row = conn.execute(
        f'SELECT {CONTACT_REFERENCE_COLUMN} FROM contacts WHERE id=?',
        (contact_id,),
    ).fetchone()
    if row is None:
        raise ContactError(f'contact inconnu : {contact_id}')
    references = load_contact_references(row[0])
    references[str(channel)] = _normalise_reference(channel, reference)
    conn.execute(
        f'UPDATE contacts SET {CONTACT_REFERENCE_COLUMN}=?, updated_at=?'
        ' WHERE id=?',
        (_dump_references(references), utcnow(), contact_id),
    )


def find_contact_by_reference(
    conn: sqlite3.Connection,
    venture_id: str,
    channel: str,
    reference: Mapping[str, Any] | str,
) -> str | None:
    """Trouve une référence dans une venture, sans index legacy parallèle."""
    wanted = _normalise_reference(channel, reference)
    wanted_value = _reference_value(wanted, channel)
    if not wanted_value:
        return None
    wanted_compare = (
        wanted_value.casefold() if channel == 'email' else wanted_value
    )
    if venture_id:
        rows = conn.execute(
            'SELECT id, contact_reference_by_canal FROM contacts'
            ' WHERE venture_id=?',
            (venture_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            'SELECT id, contact_reference_by_canal FROM contacts'
        ).fetchall()
    for row in rows:
        found = load_contact_references(row[1]).get(channel, {})
        found_value = _reference_value(found, channel)
        found_compare = (
            found_value.casefold() if channel == 'email' else found_value
        )
        if found_compare and found_compare == wanted_compare:
            return str(row[0])
    return None


def _reference_values(
    channel: str, reference: Mapping[str, Any]
) -> tuple[tuple[str, str], ...]:
    """Retourne les identifiants JSON comparables d'une référence."""
    del channel
    values: list[tuple[str, str]] = []
    for field in ('address', 'phone', 'handle', 'profile_url'):
        value = reference.get(field)
        if isinstance(value, str) and value.strip():
            values.append(
                (field, unicodedata.normalize('NFKC', value.strip()))
            )
    return tuple(values)


def _same_reference_value(
    left_channel: str,
    left_field: str,
    left_value: str,
    right_channel: str,
    right_field: str,
    right_value: str,
) -> bool:
    """Compare deux identifiants sans rendre les handles insensibles à la casse."""
    if (
        left_channel == 'email'
        or right_channel == 'email'
        or left_field == 'address'
        or right_field == 'address'
    ):
        return left_value.casefold() == right_value.casefold()
    return left_value == right_value


def _matched_contact_references(
    conn: sqlite3.Connection,
    venture_id: str,
    references: Mapping[str, Mapping[str, Any]],
) -> dict[str, list[dict[str, str]]]:
    """Associe chaque référence fournie à toutes les références de la venture."""
    rows = conn.execute(
        'SELECT id, contact_reference_by_canal FROM contacts WHERE venture_id=?',
        (venture_id,),
    ).fetchall()
    matched: dict[str, list[dict[str, str]]] = {}
    for channel, wanted in references.items():
        for wanted_field, wanted_value in _reference_values(channel, wanted):
            for row in rows:
                found_references = load_contact_references(row[1])
                for found_channel, found in found_references.items():
                    for found_field, found_value in _reference_values(
                        found_channel, found
                    ):
                        if not _same_reference_value(
                            channel,
                            wanted_field,
                            wanted_value,
                            found_channel,
                            found_field,
                            found_value,
                        ):
                            continue
                        ident = str(row[0])
                        matched.setdefault(ident, []).append(
                            {
                                'input_channel': channel,
                                'existing_channel': found_channel,
                            }
                        )
                        break
                    else:
                        continue
                    break
    return matched


def upsert_contact_references(
    conn: sqlite3.Connection,
    venture_id: str,
    display: str,
    references: Mapping[str, Any],
) -> dict[str, Any]:
    """Crée ou enrichit un contact à partir de références JSON uniquement.

    La recherche compare chaque référence entrante à tous les canaux existants
    de la venture. Une requête qui relie deux contacts déjà distincts est
    refusée plutôt que de choisir silencieusement une fiche à enrichir.
    """
    venture = str(venture_id or '').strip()
    name = str(display or '').strip()
    if not venture:
        raise ContactError('venture_id requis')
    if not name:
        raise ContactError('display requis')

    normalised = normalise_contact_references(references)
    active = {
        channel: reference
        for channel, reference in normalised.items()
        if bool(reference.get('active', True))
        and bool(_reference_values(channel, reference))
    }
    if not active:
        raise ContactError('au moins une référence active est requise')

    matched = _matched_contact_references(conn, venture, active)
    if len(matched) > 1:
        return {
            'ok': False,
            'code': 'duplicate',
            'matched_contact_ids': sorted(matched),
            'matched_reference': [
                {'contact_id': ident, **item}
                for ident in sorted(matched)
                for item in matched[ident]
            ],
        }

    if not matched:
        ident = insert_contact(conn, venture, name, active)
        return {
            'ok': True,
            'created': True,
            'enriched': False,
            'contact_id': ident,
            'channels': sorted(active),
        }

    ident = next(iter(matched))
    row = conn.execute(
        'SELECT display, contact_reference_by_canal FROM contacts WHERE id=?',
        (ident,),
    ).fetchone()
    if row is None:
        raise ContactError(f'contact inconnu : {ident}')
    current = load_contact_references(row[1])
    for channel, reference in active.items():
        merged = dict(current.get(channel, {}))
        merged.update(
            {
                key: value
                for key, value in reference.items()
                if key == 'active'
                or not (isinstance(value, str) and not value.strip())
            }
        )
        merged['active'] = True
        current[channel] = merged
    conn.execute(
        'UPDATE contacts SET contact_reference_by_canal=?, updated_at=?'
        ' WHERE id=?',
        (_dump_references(current), utcnow(), ident),
    )
    if not str(row[0] or '').strip() and name:
        conn.execute(
            'UPDATE contacts SET display=?, updated_at=? WHERE id=?',
            (name, utcnow(), ident),
        )
    return {
        'ok': True,
        'created': False,
        'enriched': True,
        'contact_id': ident,
        'channels': sorted(active),
        'matched_reference': [
            {
                'input_channel': item['input_channel'],
                'existing_channel': item['existing_channel'],
            }
            for item in matched[ident]
        ],
    }


def contact_references(
    conn: sqlite3.Connection, contact_id: str
) -> dict[str, dict[str, Any]]:
    """Lit toutes les références d’un contact."""
    row = conn.execute(
        f'SELECT {CONTACT_REFERENCE_COLUMN} FROM contacts WHERE id=?',
        (contact_id,),
    ).fetchone()
    if row is None:
        raise ContactError(f'contact inconnu : {contact_id}')
    return load_contact_references(row[0])


def insert_contact(
    conn: sqlite3.Connection,
    venture_id: str,
    display: str,
    references: Mapping[str, Mapping[str, Any]] | None = None,
) -> str:
    """Insère un contact NEW OUTBOUND avec ses références JSON."""
    contact_id = _new_id()
    moment = utcnow()
    references = normalise_contact_references(references or {})
    conn.execute(
        'INSERT INTO contacts(id, venture_id, display,'
        ' contact_reference_by_canal, regime, funnel_state, created_at,'
        ' updated_at)'
        ' VALUES(?,?,?,?,?,?,?,?)',
        (
            contact_id,
            venture_id,
            display,
            _dump_references(references or {}),
            'OUTBOUND',
            'NEW',
            moment,
            moment,
        ),
    )
    return contact_id


def create_contact(
    conn: sqlite3.Connection,
    venture_id: str,
    display: str,
    contact_reference_by_canal: Mapping[str, Any] | None = None,
    email: str = '',
    phone: str = '',
    *,
    reference: Mapping[str, Any] | None = None,
) -> str:
    """Crée un contact NEW OUTBOUND, avec une map de références JSON.

    ``contact_reference_by_canal`` peut être la map canonique ou une référence
    structurée unique ``{'channel': 'email', 'address': '...'}``. Les
    arguments email/phone restent des raccourcis d’entrée et sont convertis
    dans la map; aucune colonne legacy n’est écrite.
    """
    if reference is not None:
        if contact_reference_by_canal is not None:
            raise ContactError('référence fournie deux fois')
        contact_reference_by_canal = reference
    references = normalise_contact_references(contact_reference_by_canal)
    if email.strip():
        references['email'] = _normalise_reference(
            'email', {'address': email.strip()}
        )
    if phone.strip():
        references['voice'] = _normalise_reference(
            'voice', {'phone': phone.strip()}
        )
    return insert_contact(conn, venture_id, display, references)


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
