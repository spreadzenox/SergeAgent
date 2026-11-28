#!/usr/bin/env python3
"""Les boîtes de Serge sur un canal, et celle d'où part un envoi.

Serge peut avoir plusieurs boîtes e-mail (décision Q120). Leur liste est un
réglage en base : page Policy, famille « Canaux », ``channels.email.mailboxes``
(des adresses séparées par des virgules). Vide : la boîte du serveur, seule,
comme avant. La relève lit chaque boîte de la liste.

D'où part un envoi, dans cet ordre (une conversation reste sur sa boîte) :

1. une réponse part de la boîte qui a reçu le message auquel elle répond ;
2. sinon, de la boîte du dernier envoi au même contact sur ce canal (une
   relance, la suite d'une conversation) ;
3. sinon, c'est un premier message : il part de la boîte de la liste qui a
   envoyé le moins de messages aujourd'hui (heure UTC), la première de la
   liste à égalité. Exemple : chevalier@ a envoyé 3 messages et casadel@ 2 ;
   le prochain premier message part de casadel@.

Une boîte vide (``''``) est celle du serveur : c'est celle de tous les
envois et messages d'avant la liste, dont les conversations y restent.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.store import utcnow
from serge.policy_store import setting_value

_SEPARATEURS = re.compile(r'[\s,;]+')


def mailboxes(conn: sqlite3.Connection, channel: str) -> tuple[str, ...]:
    """Les boîtes d'un canal, dans l'ordre de la page Policy, en minuscules,
    sans doublon ; ``()`` : la boîte du serveur seulement."""
    raw = str(setting_value(conn, f'channels.{channel}.mailboxes') or '')
    found = (a.lower() for a in _SEPARATEURS.split(raw) if '@' in a)
    return tuple(dict.fromkeys(found))


def sender_for(conn: sqlite3.Connection, touch: dict[str, Any]) -> str:
    """La boîte d'où part l'envoi ``touch`` (une ligne de ``touches``)."""
    channel = str(touch['channel'])
    boxes = mailboxes(conn, channel)
    if not boxes:
        return ''
    if touch.get('reply_to'):
        row = conn.execute(
            'SELECT mailbox FROM inbound_events WHERE id=? AND channel=?',
            (str(touch['reply_to']), channel),
        ).fetchone()
        if row is not None:
            return str(row[0])
    if touch.get('contact_id'):
        row = conn.execute(
            'SELECT sender FROM touches WHERE contact_id=? AND channel=?'
            " AND id<>? AND status IN ('sent', 'sending')"
            ' ORDER BY created_at DESC LIMIT 1',
            (str(touch['contact_id']), channel, str(touch['id'])),
        ).fetchone()
        if row is not None:
            return str(row[0])
    jour = f'{utcnow()[:10]}%'
    sent = dict(
        conn.execute(
            'SELECT sender, COUNT(*) FROM touches WHERE channel=?'
            " AND status='sent' AND sent_at LIKE ? GROUP BY sender",
            (channel, jour),
        ).fetchall()
    )
    return min(boxes, key=lambda box: int(sent.get(box, 0)))
