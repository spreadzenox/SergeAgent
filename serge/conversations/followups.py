#!/usr/bin/env python3
"""Préparer les relances : qui n'a pas répondu, et depuis assez longtemps.

Une relance part sur le canal du premier message. Les délais et le nombre
de relances sont des réglages de l'invocation qui s'en sert, donnés en
paramètres. Exemple (décision Q79) : la première 3 jours (4320 minutes)
après le premier message, la suivante 7 jours (10080 minutes) après la
précédente, deux au plus.

Un contact est relancé quand :

- son premier message est parti, et le dernier envoi (premier message ou
  relance) est terminé : parti, annulé ou en échec ;
- il n'a rien écrit depuis ce dernier envoi (une réponse automatique
  d'absence, marquée ``ignored``, ne compte pas) ;
- le délai de la relance suivante est passé, et il en reste une à faire ;
- il n'est pas à une étape où Serge n'écrit plus de lui-même (refus,
  désinscription, client… : ``contacts.stop_states``, page Policy) ;
- les messages de son canal ont été relevés il y a moins de
  ``channels.<canal>.max_poll_age_minutes`` : on ne relance jamais à
  l'aveugle (décision Q37).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from serge.conversations.send import stop_states
from serge.db.store import utcnow
from serge.policy_store import setting_value

WAITING = frozenset({'to_write', 'pending', 'sending'})


def _polled_recently(
    conn: sqlite3.Connection, channel: str, now: datetime
) -> bool:
    row = conn.execute(
        'SELECT polls, polled_at FROM canaux WHERE id=?', (channel,)
    ).fetchone()
    if row is None:
        return False
    if not int(row[0]):
        return True
    age = setting_value(conn, f'channels.{channel}.max_poll_age_minutes')
    if not row[1] or age is None:
        return False
    polled = datetime.fromisoformat(str(row[1]))
    return now - polled <= timedelta(minutes=float(age))


def _due(
    conn: sqlite3.Connection,
    contact: str,
    delays: list[float],
    now: datetime,
) -> dict[str, Any] | None:
    """La relance à écrire pour ce contact, ou ``None``."""
    touches = conn.execute(
        'SELECT id, kind, status, channel, address, subject, sent_at,'
        ' updated_at FROM touches WHERE contact_id=?'
        " AND kind IN ('first', 'followup') ORDER BY created_at",
        (contact,),
    ).fetchall()
    first = next((t for t in touches if t[1] == 'first'), None)
    if first is None or first[2] != 'sent':
        return None
    last = touches[-1]
    done = sum(1 for t in touches if t[1] == 'followup')
    if last[2] in WAITING or done >= len(delays):
        return None
    since = str(last[6] or last[7])
    if conn.execute(
        'SELECT 1 FROM inbound_events WHERE contact_id=? AND received_at>?'
        " AND status<>'ignored'",
        (contact, since),
    ).fetchone():
        return None
    if now < datetime.fromisoformat(since) + timedelta(minutes=delays[done]):
        return None
    if not _polled_recently(conn, str(first[3]), now):
        return None
    return {
        'contact_id': contact,
        'channel': str(first[3]),
        'address': str(first[4]),
        'subject': str(first[5]),
        'followup_of': str(last[0]),
    }


def due_followups(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], _inv: str
) -> dict[str, Any]:
    """Capacité « Trouver les relances à faire » : une ligne par contact.

    Paramètres : ``first_delay_minutes`` (avant la première relance),
    ``next_delay_minutes`` (entre deux relances) et ``max_followups``.

    Raccourci : chaque contact qui a reçu un premier message est relu à
    chaque passage ; passer à une requête unique au-delà de 10 000
    contacts.
    """
    first = float(args.get('first_delay_minutes') or 0)
    following = float(args.get('next_delay_minutes') or 0)
    delays = [
        first if n == 0 else following
        for n in range(int(float(args.get('max_followups') or 0)))
    ]
    now = datetime.fromisoformat(utcnow())
    rows = []
    stopped = set(stop_states(conn))
    for contact, venture, state in conn.execute(
        'SELECT DISTINCT c.id, c.venture_id, c.funnel_state FROM contacts c'
        " JOIN touches t ON t.contact_id=c.id AND t.kind='first'"
    ).fetchall():
        if str(state) in stopped:
            continue
        found = _due(conn, str(contact), delays, now)
        if found:
            rows.append({**found, 'venture_id': str(venture)})
    return {'ok': True, 'rows': rows}
