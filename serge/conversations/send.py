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
   - un premier message ou une relance à un contact à une étape où Serge
     n'écrit plus de lui-même (``contacts.stop_states``, page Policy :
     refus, client, injoignable…) ;
   - une réponse ou une relance, alors que le contact a écrit depuis
     qu'elle a été écrite (la réponse suivante répondra à tout le fil).
     Un message ``ignored`` (une réponse automatique d'absence) ne compte
     pas ;
   - une réponse, alors qu'une réponse plus récente est écrite ;
4. une réponse part par le canal que la policy préfère pour la suite d'un
   message de ce canal (``channels.<canal>.reply_by``) : après un appel,
   par e-mail si Serge a l'adresse, sinon par un rappel (décision Q83) ;
5. les garde-fous (``serge/guards``) : un envoi refusé est annulé, avec sa
   raison ; un appel hors des heures d'appel attend le prochain créneau ;
   le plafond du jour du canal (``channels.<canal>.max_per_day``, page
   Policy) atteint, l'envoi attend le lendemain ; un canal qui ne peut pas
   maintenant (``ChannelLater``) fait attendre aussi ;
6. ``sending`` enregistré en base, l'envoi, puis ``sent`` et la référence
   du canal enregistrés. Le texte part avec la phrase de fin du canal
   (``footer_<canal>``, page Pipeline : « Répondez STOP… » pour
   l'e-mail).

C'est une capacité qui agit hors de Serge (``acts_outside``) : elle
enregistre en base pendant la tâche, pour qu'un arrêt du programme ne
fasse jamais partir un message deux fois. Décision Q79.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from serge.channels.adapters import ADAPTERS, adapter
from serge.channels.base import ChannelError, ChannelLater, Outgoing
from serge.db.store import append_event, utcnow
from serge.funnels.contacts import normalise_value
from serge.guards import Reason, check
from serge.interpreter.intro import serge_text
from serge.interpreter.tasks import enqueue_task
from serge.policy_store import policy_en_vigueur, setting_value

OPTED_OUT = 'OPTED_OUT'


def stop_states(conn: sqlite3.Connection) -> list[str]:
    """Les étapes où Serge n'écrit plus de lui-même (page Policy)."""
    return [str(s) for s in setting_value(conn, 'contacts.stop_states') or []]


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
    # Une étape où Serge n'écrit plus de lui-même (refus, client…, page
    # Policy) : plus de premier message ni de relance, mais on répond
    # encore à ce qu'il écrit.
    if kind != 'reply' and state in stop_states(conn):
        return 'contact à une étape où Serge n’écrit plus'
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


def _outgoing(conn: sqlite3.Connection, touch: dict[str, Any]) -> Outgoing:
    footer = serge_text(conn, f'footer_{touch["channel"]}')
    body = str(touch['body'])
    return Outgoing(
        touch_id=str(touch['id']),
        channel=str(touch['channel']),
        address=str(touch['address']),
        subject=str(touch['subject']),
        body=f'{body}\n\n{footer}' if footer else body,
        in_reply_to=str(touch['reply_ref']),
        kind=str(touch['kind']),
    )


def _day_full(conn: sqlite3.Connection, channel: str) -> str:
    """Le moment où l'envoi pourra partir si le plafond du jour du canal
    est atteint (à minuit, heure UTC), sinon ``''``."""
    cap = setting_value(conn, f'channels.{channel}.max_per_day')
    if cap is None:
        return ''
    now = datetime.fromisoformat(utcnow())
    sent = conn.execute(
        "SELECT COUNT(*) FROM touches WHERE channel=? AND status='sent'"
        ' AND sent_at LIKE ?',
        (channel, f'{now.date().isoformat()}%'),
    ).fetchone()[0]
    if int(sent) < int(cap):
        return ''
    tomorrow = now + timedelta(days=1)
    return tomorrow.replace(
        hour=0, minute=0, second=0, microsecond=0
    ).isoformat()


def _reply_route(
    conn: sqlite3.Connection, touch: dict[str, Any]
) -> dict[str, Any]:
    """La suite d'un message reçu, par le canal que la policy préfère.

    Exemple : après un appel, ``channels.voice.reply_by`` vaut ``email`` ;
    si Serge a l'adresse e-mail du contact (et que l'e-mail est branché),
    la suite part par e-mail, sinon Serge rappelle (décision Q83).
    """
    preferred = setting_value(conn, f'channels.{touch["channel"]}.reply_by')
    other = ADAPTERS.get(str(preferred or ''))
    if (
        touch['kind'] != 'reply'
        or other is None
        or other.id == touch['channel']
        or not other.ready()
    ):
        return touch
    row = conn.execute(
        'SELECT value FROM contact_addresses WHERE contact_id=? AND channel=?'
        ' AND active=1 ORDER BY created_at DESC LIMIT 1',
        (str(touch['contact_id']), other.address_channel),
    ).fetchone()
    if row is None:
        return touch
    conn.execute(
        'UPDATE touches SET channel=?, address=?, reply_to=?, updated_at=?'
        ' WHERE id=?',
        (other.id, str(row[0]), '', utcnow(), str(touch['id'])),
    )
    return _touch(conn, str(touch['id'])) or touch


def _wait(
    conn: sqlite3.Connection,
    inv: str,
    touch: dict[str, Any],
    until: str,
    reason: str,
) -> dict[str, Any]:
    """L'envoi attend ``until`` : la même invocation le reprendra."""
    enqueue_task(
        conn,
        inv,
        {'touch_id': str(touch['id'])},
        origin_ref=f'{reason} : {touch["id"]}',
        not_before=until,
        key=f'{touch["id"]}:{until}',
    )
    return {
        'ok': True,
        'status': 'pending',
        'retry_at': until,
        'reason': reason,
    }


def send_message(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Envoyer un message » : ``{touch_id}``.

    Rend le statut final de l'envoi : ``sent``, ``cancelled`` (devenu
    inutile, ou refusé par un garde-fou : la raison est dans
    ``last_error``), ``failed`` (le canal a refusé le message) ou
    ``pending`` avec ``retry_at`` (il attend : le plafond du jour, ou le
    prochain créneau d'appel). Une panne imprévue fait échouer la tâche et
    l'envoi reste ``sending`` : la tâche relancée demandera au canal s'il
    est parti.
    """
    touch = _touch(conn, str(args.get('touch_id') or ''))
    if touch is None:
        return {'ok': False, 'code': 'envoi_inconnu'}
    status = str(touch['status'])
    if status in ('sent', 'cancelled'):
        return {'ok': True, 'status': status}
    if status == 'pending':
        reason = _outdated(conn, touch)
        if reason:
            _set(conn, touch, 'cancelled', last_error=reason)
            return {'ok': True, 'status': 'cancelled', 'reason': reason}
        touch = _reply_route(conn, touch)
    elif status != 'sending':
        return {'ok': False, 'code': f'statut_{status}'}
    channel = adapter(str(touch['channel']))
    message = _outgoing(conn, touch)
    if status == 'sending':
        ref = channel.confirm(message)
        if ref:
            _set(conn, touch, 'sent', external_ref=ref, sent_at=utcnow())
            return {'ok': True, 'status': 'sent', 'confirmed': True}
    else:
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
        if verdict.reason == Reason.OUTSIDE_WINDOW and verdict.retry_at:
            return _wait(conn, inv, touch, verdict.retry_at, 'hors créneau')
        if not verdict.allowed:
            reason = verdict.reason.value
            _set(conn, touch, 'cancelled', last_error=reason)
            return {'ok': True, 'status': 'cancelled', 'reason': reason}
        later = _day_full(conn, str(touch['channel']))
        if later:
            return _wait(conn, inv, touch, later, 'plafond du jour')
        _set(conn, touch, 'sending')
    try:
        ref = channel.send(message)
    except ChannelLater as exc:
        _set(conn, touch, 'pending', last_error=str(exc))
        return _wait(conn, inv, touch, exc.until, str(exc))
    except ChannelError as exc:
        _set(conn, touch, 'failed', last_error=str(exc))
        return {'ok': False, 'status': 'failed', 'reason': str(exc)}
    _set(conn, touch, 'sent', external_ref=ref, sent_at=utcnow())
    return {'ok': True, 'status': 'sent'}
