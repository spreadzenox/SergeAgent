#!/usr/bin/env python3
"""Envoyer un message écrit dans ``touches``, jamais deux fois.

Un envoi est écrit (statut ``pending``) avant de partir. Au moment de
partir, dans cet ordre :

1. déjà ``sent`` ou ``cancelled`` : rien ;
2. ``sending`` (le programme s'est arrêté pendant un envoi) : on demande au
   canal s'il est parti (``confirm``). Parti : il est marqué ``sent``.
   Sinon il est envoyé ;
3. devenu inutile, il est annulé :
   - la personne s'est désinscrite ;
   - un premier message ou une relance à un contact dans un état final
     (il a refusé, il est client, injoignable…) ;
   - une réponse ou une relance, alors que le contact a écrit depuis
     qu'elle a été écrite (la réponse suivante répondra à tout le fil).
     Un message ``ignored`` (une réponse automatique d'absence) ne compte
     pas ;
   - une réponse, alors qu'une réponse plus récente est écrite ;
4. sinon les garde-fous (``serge/guards``) : un envoi refusé est annulé,
   avec sa raison. Puis ``sending`` enregistré en base, l'envoi, puis
   ``sent`` et la référence du canal enregistrés.

C'est une capacité qui agit hors de Serge (``acts_outside``) : elle
enregistre en base pendant la tâche, pour qu'un arrêt du programme ne
fasse jamais partir un message deux fois. Décision Q79.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.channels.base import ChannelError, Outgoing, adapter
from serge.db.store import append_event, utcnow
from serge.funnels.contact_errors import TERMINAL
from serge.funnels.contacts import normalise_value
from serge.guards import check
from serge.policy_store import policy_en_vigueur

OPTED_OUT = 'OPTED_OUT'


def _touch(conn: sqlite3.Connection, touch_id: str) -> dict[str, Any] | None:
    """L'envoi, l'état du contact, et le message auquel il fait suite.

    Une réponse fait suite au message reçu ; une relance, à l'envoi
    qu'elle relance (pour rester dans le même fil d'e-mail).
    """
    cursor = conn.execute(
        "SELECT t.*, COALESCE(c.funnel_state, '') AS funnel_state,"
        " COALESCE(i.message_ref, f.external_ref, '') AS reply_ref,"
        " COALESCE(k.address_channel, '') AS address_channel"
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' LEFT JOIN inbound_events i ON i.id=t.reply_to'
        ' LEFT JOIN touches f ON f.id=t.followup_of'
        ' LEFT JOIN canaux k ON k.id=t.channel WHERE t.id=?',
        (touch_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cursor.description], row, strict=True))


def _outdated(conn: sqlite3.Connection, touch: dict[str, Any]) -> str:
    """Pourquoi l'envoi est devenu inutile, ou ``''``."""
    state = str(touch['funnel_state'])
    kind = str(touch['kind'])
    if state == OPTED_OUT:
        return 'contact désinscrit'
    # Un état final (refus, client, injoignable…) : plus de premier
    # message ni de relance, mais on répond encore à ce qu'il écrit.
    if kind != 'reply' and state in TERMINAL:
        return 'contact dans un état final'
    if kind == 'first':
        return ''
    contact, written = str(touch['contact_id']), str(touch['created_at'])
    if conn.execute(
        'SELECT 1 FROM inbound_events WHERE contact_id=? AND received_at>?'
        " AND status<>'ignored'",
        (contact, written),
    ).fetchone():
        return 'le contact a écrit depuis'
    # Deux messages coup sur coup pendant qu'une réponse s'écrivait : seule
    # la plus récente part, elle a lu tout le fil.
    if (
        kind == 'reply'
        and conn.execute(
            "SELECT 1 FROM touches WHERE contact_id=? AND kind='reply'"
            " AND status<>'cancelled' AND created_at>? AND id<>?",
            (contact, written, str(touch['id'])),
        ).fetchone()
    ):
        return 'une réponse plus récente est écrite'
    return ''


def _set(
    conn: sqlite3.Connection, touch: dict[str, Any], status: str, **extra: str
) -> None:
    """Change le statut de l'envoi, au journal, et l'enregistre."""
    sets = ', '.join(f'{k}=?' for k in ('status', 'updated_at', *extra))
    conn.execute(
        f'UPDATE touches SET {sets} WHERE id=?',
        (status, utcnow(), *extra.values(), str(touch['id'])),
    )
    append_event(
        conn,
        actor='conversations',
        type=f'touch.{status}',
        venture_id=str(touch['venture_id']),
        payload={'channel': str(touch['channel']), **extra},
        rows=[('touches', touch['id']), ('contacts', touch['contact_id'])],
    )
    conn.commit()


def _outgoing(touch: dict[str, Any]) -> Outgoing:
    return Outgoing(
        touch_id=str(touch['id']),
        channel=str(touch['channel']),
        address=str(touch['address']),
        subject=str(touch['subject']),
        body=str(touch['body']),
        in_reply_to=str(touch['reply_ref']),
        kind=str(touch['kind']),
    )


def send_message(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Envoyer un message » : ``{touch_id}``.

    Rend le statut final de l'envoi : ``sent``, ``cancelled`` (devenu
    inutile, ou refusé par un garde-fou : la raison est dans
    ``last_error``) ou ``failed`` (le canal a refusé le message). Une
    panne imprévue fait échouer la tâche et l'envoi reste ``sending`` : la
    tâche relancée demandera au canal s'il est parti.
    """
    touch = _touch(conn, str(args.get('touch_id') or ''))
    if touch is None:
        return {'ok': False, 'code': 'envoi_inconnu'}
    status = str(touch['status'])
    if status in ('sent', 'cancelled'):
        return {'ok': True, 'status': status}
    channel = adapter(str(touch['channel']))
    message = _outgoing(touch)
    if status == 'sending':
        ref = channel.confirm(message)
        if ref:
            _set(conn, touch, 'sent', external_ref=ref, sent_at=utcnow())
            return {'ok': True, 'status': 'sent', 'confirmed': True}
    elif status != 'pending':
        return {'ok': False, 'code': f'statut_{status}'}
    else:
        reason = _outdated(conn, touch)
        if reason:
            _set(conn, touch, 'cancelled', last_error=reason)
            return {'ok': True, 'status': 'cancelled', 'reason': reason}
        verdict = check(
            conn,
            policy_en_vigueur(conn),
            {
                'channel': touch['channel'],
                'subject': normalise_value(
                    str(touch['address_channel']), str(touch['address'])
                ),
                'idempotency_key': touch['idempotency_key'],
                'touch_id': touch['id'],
                'kind': touch['kind'],
                'contact_id': touch['contact_id'],
            },
        )
        if not verdict.allowed:
            reason = verdict.reason.value
            _set(conn, touch, 'cancelled', last_error=reason)
            return {'ok': True, 'status': 'cancelled', 'reason': reason}
        _set(conn, touch, 'sending')
    try:
        ref = channel.send(message)
    except ChannelError as exc:
        _set(conn, touch, 'failed', last_error=str(exc))
        return {'ok': False, 'status': 'failed', 'reason': str(exc)}
    _set(conn, touch, 'sent', external_ref=ref, sent_at=utcnow())
    return {'ok': True, 'status': 'sent'}
