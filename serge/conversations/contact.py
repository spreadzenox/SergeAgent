#!/usr/bin/env python3
"""Créer un contact, le trouver, noter une adresse qu'il donne.

- « Créer un contact » : une fiche, ses adresses et, au besoin, son accord
  pour être appelé. Exemple : le bouton d'essai de Mission Control crée la
  fiche de Clem avec l'accord « test » (décision Q79).
- « Chercher un contact » et « Noter une adresse », pour l'agent vocal : un
  appelant inconnu dit son nom ou son e-mail, l'agent cherche sa fiche ;
  une personne qui veut recevoir un document donne son e-mail, l'agent le
  note sur sa fiche (décision Q83).
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow
from serge.funnels.contact_errors import ContactError
from serge.funnels.contacts import add_address, create_contact, normalise_value
from serge.policy_store import setting_value
from serge.privacy import subject_hash

# Les fiches rendues au plus par une recherche.
SEARCH_MAX = 5
_EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
_PHONE = re.compile(r'\+[1-9][0-9]{7,14}')
# Les accords qu'une fiche peut porter pour être appelée.
CALL_CONSENTS = frozenset({'consent', 'test'})
# L'indicatif d'un pays : un numéro national (0768…) du pays par défaut
# (page Policy, « Pays et appels ») devient international (+33768…).
COUNTRY_CODES = {'FR': '33'}


def _international(conn: sqlite3.Connection, raw: str) -> str:
    """Un numéro au format international, ou ``''``.

    Exemple : ``07 68 12 34 56`` en France donne ``+33768123456``.
    """
    phone = normalise_value('phone', raw)
    if phone.startswith('0') and len(phone) == 10:
        zone = str(setting_value(conn, 'calling_zones.default') or '')
        code = COUNTRY_CODES.get(zone)
        phone = f'+{code}{phone[1:]}' if code else phone
    return phone


def _unblock_for_test(
    conn: sqlite3.Connection, addresses: list[str], contact: str, inv: str
) -> None:
    """Relancer un essai lève la désinscription de ces adresses-là.

    Un membre de l'équipe qui a essayé « STOP » doit pouvoir réessayer :
    c'est lui qui retape ses adresses dans Mission Control. Seul un blocage
    venu d'une désinscription est levé ; c'est noté au journal.
    """
    digests = [subject_hash(a) for a in addresses if a]
    holes = ','.join('?' * len(digests))
    lifted = conn.execute(
        f'DELETE FROM blocklist WHERE subject_hash IN ({holes})'
        " AND reason='désinscription'",
        digests,
    ).rowcount
    if lifted:
        append_event(
            conn,
            actor=f'invocation:{inv}',
            type='contact.unblocked_for_test',
            payload={'addresses': lifted},
            rows=[('contacts', contact)],
        )


def add_contact(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Créer un contact » : ``{venture_id, name, email, phone,
    call_consent}``.

    Crée la fiche et ses adresses ; ``call_consent`` (``consent`` ou
    ``test``) note l'accord de la personne pour être appelée sur ce numéro.
    Un numéro national du pays par défaut est mis au format international.
    Avec l'accord ``test`` (un membre de l'équipe qui essaie Serge), la
    désinscription de ces adresses est levée. Rend la fiche créée
    (``rows``), avec ses adresses remises en forme.

    Raises:
        ValueError: Une adresse invalide (un e-mail sans @, un numéro qui
            n'est pas au format international ``+33…``) ; la tâche échoue
            avec la raison, rien n'est créé.
    """
    name = str(args.get('name') or '').strip()
    email = str(args.get('email') or '').strip()
    phone = _international(conn, str(args.get('phone') or ''))
    consent = str(args.get('call_consent') or '')
    if not name or not (email or phone):
        raise ValueError(
            'un nom et une adresse (e-mail ou numéro) sont requis'
        )
    if email and not _EMAIL.fullmatch(email):
        raise ValueError(f'adresse e-mail invalide : {email}')
    if phone and not _PHONE.fullmatch(phone):
        raise ValueError('numéro au format international attendu (+33…)')
    if consent and consent not in CALL_CONSENTS:
        raise ValueError(f'accord inconnu : {consent}')
    venture = str(args.get('venture_id') or '')
    contact = create_contact(conn, venture, name, email=email, phone=phone)
    if consent and phone:
        digest = subject_hash(phone)
        conn.execute(
            'INSERT INTO consents(id, channel, subject_hash, subject_ref,'
            " basis, granted_at, revoked_at) VALUES(?, 'voice', ?, ?, ?, ?, '')"
            ' ON CONFLICT(channel, subject_hash) DO UPDATE SET'
            ' basis=excluded.basis, granted_at=excluded.granted_at,'
            " revoked_at=''",
            (f'voice_{digest}', digest, contact, consent, utcnow()),
        )
    if consent == 'test':
        _unblock_for_test(
            conn, [normalise_value('email', email), phone], contact, inv
        )
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='contact.created',
        venture_id=venture,
        payload={'call_consent': consent},
        rows=[('contacts', contact)],
    )
    row = {
        'contact_id': contact,
        'venture_id': venture,
        'email': normalise_value('email', email),
        'phone': phone,
    }
    return {'ok': True, 'rows': [row]}


def contact_search(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Chercher un contact » : ``{query}``.

    Cherche par e-mail ou numéro exacts, sinon par un morceau du nom (une
    fiche peut porter l'entreprise : « Marc (Acme) »). Rend au plus 5
    fiches : numéro, nom, business, étape. Jamais ses adresses ni son fil :
    une personne reconnue seulement par son nom n'entend aucune information
    sensible.
    """
    query = str(args.get('query') or '').strip()
    if len(query) < 3:
        return {'ok': False, 'code': 'recherche_trop_courte', 'rows': []}
    found = conn.execute(
        "SELECT DISTINCT c.id, c.display, COALESCE(v.name, ''),"
        ' c.funnel_state FROM contacts c'
        ' LEFT JOIN ventures v ON v.id=c.venture_id'
        ' LEFT JOIN contact_addresses a ON a.contact_id=c.id'
        " WHERE (a.channel='email' AND a.value_norm=?)"
        " OR (a.channel='phone' AND a.value_norm=?)"
        ' OR c.display LIKE ? ORDER BY c.created_at DESC LIMIT ?',
        (
            normalise_value('email', query),
            normalise_value('phone', query) or '-',
            f'%{query}%',
            SEARCH_MAX,
        ),
    ).fetchall()
    rows = [
        {
            'id': str(r[0]),
            'name': str(r[1]),
            'business': str(r[2]),
            'stage': str(r[3]),
        }
        for r in found
    ]
    return {'ok': True, 'rows': rows}


def add_contact_address(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Noter une adresse » : ``{contact_id, channel, value}``.

    Ajoute l'adresse à la fiche, à côté des autres (une adresse n'est
    jamais écrasée). Exemple : ``email``, ``marc@acme.fr``.
    """
    contact = str(args.get('contact_id') or '')
    channel = str(args.get('channel') or '')
    value = str(args.get('value') or '').strip()
    if channel not in ('email', 'phone'):
        return {'ok': False, 'code': 'sorte_d_adresse_inconnue'}
    if channel == 'email' and not _EMAIL.fullmatch(value):
        return {'ok': False, 'code': 'adresse_e-mail_invalide'}
    try:
        added = add_address(conn, contact, channel, value)
    except ContactError as exc:
        return {'ok': False, 'code': str(exc)}
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='contact.address_added',
        payload={'channel': channel, 'added': added},
        rows=[('contacts', contact)],
    )
    return {'ok': True, 'added': added}
