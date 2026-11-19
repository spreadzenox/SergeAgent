#!/usr/bin/env python3
"""Ajouter un prospect à une campagne, après vérification.

« Ajouter un prospect » est l'outil de « Trouver des prospects » : le
modèle propose une personne, le code vérifie tout de suite et dit pourquoi
il refuse, pour que le modèle cherche quelqu'un d'autre. Refusés
(décisions Q36 et Q93) : une adresse sans la page où elle a été trouvée,
une adresse mal formée, **une adresse générique** (``contact@``, ``info@``
… : la liste est un réglage, page Policy, « Contacts »), un domaine qui ne
reçoit pas d'e-mails, une personne désinscrite ou déjà contactée pour ce
business, une campagne qui a son compte.

Un prospect accepté devient un contact, avec son adresse (et sa source)
et un premier message « à rédiger » sur le canal de la campagne.
"""

from __future__ import annotations

import re
import sqlite3
import uuid
from typing import Any

from serge.campaigns.follow import found
from serge.campaigns.mx import Resolver, receives_mail
from serge.campaigns.start import campaign
from serge.db.store import append_event, utcnow
from serge.funnels.contacts import create_contact, normalise_value
from serge.interpreter.settings import load_settings
from serge.interpreter.triggers import notify_rows_written
from serge.policy_store import setting_value
from serge.privacy import subject_hash
from serge.trial import current_task

_EMAIL = re.compile(r'[^@\s]+@[^@\s]+\.[^@\s]+')
_PHONE = re.compile(r'\+[1-9][0-9]{7,14}')


def _refuse(raison: str) -> dict[str, Any]:
    return {'ok': False, 'refus': raison}


def _profile_refusal(conn: sqlite3.Connection, kind: str, address: str) -> str:
    """Pour un canal du navigateur, l'adresse d'un prospect est celle de
    son profil sur le site du canal. Rend le refus, ou ``''``."""
    row = conn.execute(
        'SELECT a.url FROM canaux k JOIN web_accounts a ON a.id=k.account'
        ' WHERE k.address_channel=?',
        (kind,),
    ).fetchone()
    if row is None:
        return ''
    site = normalise_value(kind, str(row[0])).split('/', 1)[0]
    profil = normalise_value(kind, address)
    hote, _, chemin = profil.partition('/')
    if (
        not address.casefold().startswith(('http://', 'https://'))
        or not chemin
        or not (hote == site or hote.endswith(f'.{site}'))
    ):
        return (
            f'adresse d’un profil attendue : celle de la personne sur'
            f' {site} (https://{site}/…), pas « {address} »'
        )
    return ''


def _address_refusal(
    conn: sqlite3.Connection,
    kind: str,
    address: str,
    resolver: Resolver | None,
    inv: str,
) -> str:
    """Pourquoi cette adresse ne convient pas, ou ``''``."""
    if kind == 'phone':
        if not _PHONE.fullmatch(address):
            return 'numéro au format international attendu (+33…)'
        return ''
    if kind != 'email':
        return ''
    if not _EMAIL.fullmatch(address):
        return 'adresse e-mail mal formée'
    local, _, domain = address.partition('@')
    generic = {
        g.strip().casefold()
        for g in str(
            setting_value(conn, 'contacts.generic_addresses') or ''
        ).split(',')
    }
    if local in generic:
        return (
            f'adresse générique ({local}@) : cherche l’adresse directe'
            ' d’une personne nommée, ou laisse cette entreprise de côté'
        )
    receives, why = receives_mail(domain, resolver)
    if receives is None:
        # Une panne du résolveur ne refuse pas l'adresse ; elle est notée.
        append_event(
            conn,
            actor=f'invocation:{inv}',
            type='prospect.domain_unchecked',
            payload={'domain': domain, 'error': why},
        )
    return '' if receives is not False else f'{why} ({domain})'


def _already(
    conn: sqlite3.Connection, venture: str, kind: str, norm: str
) -> bool:
    return (
        conn.execute(
            'SELECT 1 FROM contact_addresses a JOIN contacts c'
            ' ON c.id=a.contact_id WHERE c.venture_id=? AND a.channel=?'
            ' AND a.value_norm=?',
            (venture, kind, norm),
        ).fetchone()
        is not None
    )


def _added_by_task(conn: sqlite3.Connection, campaign_id: str) -> int:
    """Les prospects déjà ajoutés par la tâche en cours."""
    row = conn.execute(
        'SELECT started_at FROM tasks WHERE id=?', (current_task(),)
    ).fetchone()
    return found(conn, campaign_id, str(row[0])) if row and row[0] else 0


def add_prospect(
    conn: sqlite3.Connection,
    _tool: str,
    args: dict[str, Any],
    inv: str,
    resolver: Resolver | None = None,
) -> dict[str, Any]:
    """Capacité « Ajouter un prospect » : ``{campaign_id, name, company,
    role, why, address, source_url}``.

    Rend ``{ok: true, contact_id, restants}`` ou ``{ok: false, refus}``.
    """
    row = campaign(conn, str(args.get('campaign_id') or ''))
    if row is None or row['state'] != 'RUNNING':
        return _refuse('cette campagne n’est pas en cours')
    name = str(args.get('name') or '').strip()
    source = str(args.get('source_url') or '').strip()
    kind = str(row['address_kind'])
    brute = str(args.get('address') or '').strip()
    address = normalise_value(kind, brute)
    # L'adresse d'un profil s'ouvre telle qu'elle est écrite ; sa forme
    # comparable ne sert qu'à reconnaître la personne.
    profil = brute.casefold().startswith(('http://', 'https://'))
    usable = brute if profil else address
    left = int(row['n_target']) - found(conn, str(row['id']))
    cap = str(load_settings(conn, inv).get('prospects_par_passage') or '')
    if left <= 0:
        return _refuse('la campagne a son compte de prospects : arrête-toi')
    if cap.isdigit() and _added_by_task(conn, str(row['id'])) >= int(cap):
        return _refuse(f'{cap} prospects ajoutés à ce passage : arrête-toi')
    if not name or not address:
        return _refuse('un nom et une adresse sont requis')
    if not source.startswith(('http://', 'https://')):
        return _refuse('la page où l’adresse a été trouvée est requise')
    raison = _profile_refusal(conn, kind, brute) or _address_refusal(
        conn, kind, address, resolver, inv
    )
    if raison:
        return _refuse(raison)
    if conn.execute(
        'SELECT 1 FROM blocklist WHERE subject_hash=?',
        (subject_hash(address),),
    ).fetchone():
        return _refuse('cette personne ne veut plus être contactée')
    venture = str(row['venture_id'])
    if _already(conn, venture, kind, address):
        return _refuse('déjà contacté pour ce business')
    company = str(args.get('company') or '').strip()
    role = str(args.get('role') or '').strip()
    who = ', '.join(p for p in (name, role) if p)
    contact = create_contact(
        conn, venture, f'{who} ({company})' if company else who
    )
    now = utcnow()
    conn.execute(
        'UPDATE contacts SET note=? WHERE id=?',
        (str(args.get('why') or '').strip(), contact),
    )
    conn.execute(
        'INSERT INTO contact_addresses(contact_id, channel, value,'
        ' value_norm, active, created_at, source_url) VALUES(?,?,?,?,1,?,?)',
        (contact, kind, usable, address, now, source),
    )
    touch = f'tou_{uuid.uuid4().hex[:12]}'
    conn.execute(
        'INSERT INTO touches(id, campaign_id, contact_id, venture_id,'
        ' channel, address, kind, status, idempotency_key, created_at,'
        " updated_at) VALUES(?,?,?,?,?,?, 'first', 'to_write', ?, ?, ?)",
        (
            touch,
            row['id'],
            contact,
            venture,
            row['channel'],
            usable,
            touch,
            now,
            now,
        ),
    )
    conn.execute(
        'UPDATE campaigns SET dry_searches=0 WHERE id=?', (row['id'],)
    )
    append_event(
        conn,
        actor=f'invocation:{inv}',
        type='prospect.added',
        venture_id=venture,
        payload={'campaign': row['id'], 'channel': row['channel']},
        rows=[('contacts', contact), ('touches', touch)],
    )
    # Le premier message « à rédiger » réveille le pipeline.
    notify_rows_written(conn, 'touches', [touch])
    return {'ok': True, 'contact_id': contact, 'restants': left - 1}
