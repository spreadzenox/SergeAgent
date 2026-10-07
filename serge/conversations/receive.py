#!/usr/bin/env python3
"""Relever les messages d'un canal et les rattacher à leur contact.

Un message reçu est rattaché, dans cet ordre (décision Q37) :

1. par le fil : il répond à un message que Serge a envoyé (une de ses
   références est celle d'un envoi connu) ;
2. par l'adresse : l'expéditeur est une adresse connue sur ce canal ; si
   plusieurs fiches la portent (une personne contactée pour deux
   business), c'est celle à qui Serge a écrit le plus récemment.

Sinon il est ``unattached`` : il n'est pas traité et apparaît dans Mission
Control, dans les messages non rattachés.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.channels.adapters import adapter
from serge.channels.base import Incoming
from serge.funnels.contacts import normalise_value


def _by_thread(conn: sqlite3.Connection, refs: tuple[str, ...]) -> Any:
    refs = tuple(r for r in refs if r)
    if not refs:
        return None
    holes = ','.join('?' * len(refs))
    return conn.execute(
        'SELECT contact_id, venture_id FROM touches'
        f" WHERE contact_id <> '' AND external_ref IN ({holes})"
        ' ORDER BY created_at DESC LIMIT 1',
        refs,
    ).fetchone()


def _by_address(
    conn: sqlite3.Connection, address_channel: str, address: str
) -> Any:
    norm = normalise_value(address_channel, address)
    if not norm:
        return None
    return conn.execute(
        'SELECT c.id, c.venture_id FROM contact_addresses a'
        ' JOIN contacts c ON c.id=a.contact_id'
        ' WHERE a.channel=? AND a.value_norm=?'
        ' ORDER BY (SELECT MAX(t.created_at) FROM touches t'
        ' WHERE t.contact_id=c.id) DESC, c.created_at DESC LIMIT 1',
        (address_channel, norm),
    ).fetchone()


def attach(
    conn: sqlite3.Connection, channel: str, message: Incoming
) -> dict[str, Any]:
    """Une ligne de ``inbound_events`` pour ce message, rattaché ou non."""
    found = _by_thread(conn, message.refs)
    if found is None:
        row = conn.execute(
            'SELECT address_channel FROM canaux WHERE id=?', (channel,)
        ).fetchone()
        found = _by_address(conn, str(row[0]) if row else '', message.address)
    return {
        'external_ref': message.external_ref,
        'address': message.address,
        'subject': message.subject,
        'body': message.body,
        'message_ref': message.message_ref,
        'native_type': message.native_type,
        'contact_id': str(found[0]) if found else '',
        'venture_id': str(found[1]) if found else '',
        'status': 'attached' if found else 'unattached',
    }


def receive_messages(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Relever les messages » d'un canal : ``{channel}``.

    Rend les messages nouveaux (``rows``), rattachés ou non ; les règles
    d'écriture de l'invocation les rangent dans ``inbound_events``, ce qui
    réveille le pipeline. Un message déjà relevé n'est pas rendu deux fois.
    """
    channel = str(args.get('channel') or '')
    poll = adapter(channel).poll
    if poll is None:
        return {'ok': False, 'code': 'sans_releve', 'rows': []}
    row = conn.execute(
        'SELECT polled_at FROM canaux WHERE id=?', (channel,)
    ).fetchone()
    rows: dict[str, dict[str, Any]] = {}
    # La relève peut relire les messages de la dernière minute : ceux déjà
    # écrits, ou rendus deux fois, sont écartés.
    for message in poll(str(row[0]) if row else ''):
        if (
            message.external_ref in rows
            or conn.execute(
                'SELECT 1 FROM inbound_events WHERE channel=? AND external_ref=?',
                (channel, message.external_ref),
            ).fetchone()
        ):
            continue
        rows[message.external_ref] = attach(conn, channel, message)
    return {'ok': True, 'rows': list(rows.values())}
