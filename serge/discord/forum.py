#!/usr/bin/env python3
"""Les tickets dans le forum « tickets » du serveur de Serge (Q88).

La base est la vérité ; le bot la recopie à chaque tour :

- un ticket ouvert après le réglage du forum (page Décisions de Mission
  Control) y ouvre un fil, avec sa carte et ses boutons, et mentionne les
  administrateurs : ils sont prévenus, à toute heure ;
- dès qu'il change (tranché sur Discord ou dans Mission Control, expiré,
  annulé, ou un nouveau brouillon après « Réécrire »), sa carte est mise à
  jour ; tranché, ses boutons sont morts, elle dit qui l'a tranché, et le
  fil est archivé.

Un fil qui n'a pas pu être ouvert, ou une carte pas mise à jour (le
forum n'existe pas, le bot n'a pas le droit d'y écrire), est réessayé
après ``RETRY_MINUTES``. Sans forum réglé, les tickets restent dans
Mission Control.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import append_event, utcnow
from serge.discord.journal import journal
from serge.discord.render import render_card
from serge.discord.rest import (
    DiscordError,
    archive_thread,
    create_forum_post,
    edit_message,
    send_message,
)
from serge.text_ids import strip_ids
from serge.tickets import get_ticket
from serge.tickets.admins import admin_name, admins
from serge.tickets.types import ticket_types

RETRY_MINUTES = 10
# L'état d'un fil qui n'a pas pu être ouvert, et d'une carte qui n'a pas pu
# être modifiée (réessayés après RETRY_MINUTES).
ECHEC = 'ECHEC'
ECHEC_MODIF = 'ECHEC_MODIF'
# La version d'un ticket : son état et sa dernière mise à jour.
VERSION = "t.state || '@' || t.updated_at"
VERDICTS = {
    'APPROVED': 'Approuvé',
    'REJECTED': 'Rejeté',
    'EDITED': 'Modifié',
    'EXECUTED': 'Fait',
    'CLOSED': 'Fait',
    'EXPIRED': 'Expiré',
    'CANCELLED': 'Annulé',
}
# Le réglage du forum : son identifiant, et quand il a été réglé.
FLAG_FORUM = 'discord.forum_tickets'
_SNOWFLAKE = re.compile(r'\d{17,20}')


def forum_tickets(conn: sqlite3.Connection) -> tuple[str, str]:
    """Le forum des tickets et l'heure de son réglage ; ``('', '')`` sans
    forum."""
    row = conn.execute(
        'SELECT value, set_at FROM runtime_flags WHERE name=?', (FLAG_FORUM,)
    ).fetchone()
    return (str(row[0]), str(row[1])) if row and row[0] else ('', '')


def regler_forum(conn: sqlite3.Connection, forum_id: str, by: str) -> str:
    """Règle le forum des tickets (vide : plus de forum) ; rend ce qui ne
    va pas, ou ``''``.

    Seuls les tickets ouverts après le réglage y ouvrent un fil : les plus
    anciens restent dans Mission Control.
    """
    forum_id = forum_id.strip()
    if forum_id and not _SNOWFLAKE.fullmatch(forum_id):
        return (
            'identifiant du forum : un nombre de 17 à 20 chiffres (clic'
            ' droit sur le salon, « Copier l’identifiant », en mode'
            ' développeur)'
        )
    if forum_id:
        conn.execute(
            'INSERT OR REPLACE INTO runtime_flags(name, value, set_by, set_at)'
            ' VALUES(?,?,?,?)',
            (FLAG_FORUM, forum_id, by, utcnow()),
        )
    else:
        conn.execute('DELETE FROM runtime_flags WHERE name=?', (FLAG_FORUM,))
    append_event(
        conn,
        actor=by,
        type='discord.forum_set',
        payload={'forum_id': forum_id},
    )
    return ''


def _tranche(conn: sqlite3.Connection, ticket: Mapping[str, Any]) -> str:
    """Qui a tranché le ticket, et comment ; ``''`` s'il est encore ouvert.

    Exemple : « Approuvé par Clem », « Rejeté dans Mission Control »,
    « Expiré : La policy actuelle reste. ».
    """
    state = str(ticket.get('state') or '')
    verdict = VERDICTS.get(state)
    if verdict is None:
        return ''
    if state == 'EXPIRED':
        detail = str(ticket.get('default_detail') or '')
        return f'{verdict} : {detail}' if detail else verdict
    row = conn.execute(
        'SELECT actor, payload_json FROM ticket_events WHERE ticket_id=?'
        ' AND kind=? ORDER BY id DESC LIMIT 1',
        (ticket['id'], f'transition.{state.lower()}'),
    ).fetchone()
    actor = str(row[0]) if row else ''
    note = ''
    if row:
        try:
            note = str(json.loads(row[1] or '{}').get('note') or '')
        except ValueError:
            note = ''
    if actor.startswith('discord:'):
        who = f' par {admin_name(conn, actor.split(":", 1)[1]) or "un administrateur"}'
    elif actor == 'owner':
        who = ' dans Mission Control'
    else:
        who = ''
    return f'{verdict}{who}' + (f' : {note}' if note else '')


def _carte(
    conn: sqlite3.Connection, ticket_id: str, now_iso: str
) -> tuple[dict[str, Any], str] | None:
    """La carte d'un ticket et le nom de son fil, ou None."""
    try:
        ticket = get_ticket(conn, ticket_id)
    except ValueError:
        return None
    spec = ticket_types(conn).get(str(ticket.get('type')))
    if not isinstance(spec, dict):
        return None
    try:
        payload = json.loads(ticket.get('payload_json') or '{}')
    except (TypeError, ValueError):
        payload = {}
    ticket = {
        **ticket,
        'payload': payload if isinstance(payload, dict) else {},
        'default_detail': spec.get('default_detail', ''),
    }
    ticket['tranche'] = _tranche(conn, ticket)
    carte = render_card(ticket, spec, now_iso=now_iso)
    emoji = str((spec.get('render') or {}).get('emoji') or '🎫')
    nom = f'{emoji} {ticket.get("title") or ticket.get("type")}'
    return carte, strip_ids(nom)


def _mentions(conn: sqlite3.Connection) -> dict[str, Any]:
    """Le texte qui mentionne les administrateurs : ils sont prévenus."""
    ids = [a['user_id'] for a in admins(conn)]
    return {
        'content': ' '.join(f'<@{i}>' for i in ids),
        'allowed_mentions': {'parse': [], 'users': ids[:100]},
    }


def _ouvrir_fils(
    conn: sqlite3.Connection, token: str, forum: str, depuis: str, now: str
) -> int:
    """Ouvre le fil de chaque ticket ouvert qui n'en a pas encore, en
    mentionnant les administrateurs ; rend le nombre de fils ouverts."""
    retry = (
        datetime.fromisoformat(now) - timedelta(minutes=RETRY_MINUTES)
    ).isoformat()
    mentions = _mentions(conn)
    count = 0
    for ticket_id, version in conn.execute(
        f'SELECT t.id, {VERSION} FROM tickets t'
        " WHERE t.state IN ('OPEN','DISCUSSING') AND t.created_at>=?"
        ' AND NOT EXISTS (SELECT 1 FROM ticket_posts p'
        ' WHERE p.ticket_id=t.id AND (p.shown_state<>? OR p.updated_at>?))'
        ' ORDER BY t.created_at',
        (depuis, ECHEC, retry),
    ).fetchall():
        rendu = _carte(conn, str(ticket_id), now)
        if rendu is None:
            continue
        carte, nom = rendu
        try:
            fil = create_forum_post(token, forum, nom, {**mentions, **carte})
            values = (fil, str(version))
        except DiscordError as exc:
            journal(f'fil du ticket {ticket_id} pas ouvert : {exc}')
            values = ('', ECHEC)
        conn.execute(
            'INSERT OR REPLACE INTO ticket_posts(ticket_id, thread_id,'
            ' shown_state, archived, updated_at) VALUES(?,?,?,0,?)',
            (ticket_id, *values, now),
        )
        conn.commit()
        count += values[1] != ECHEC
    return count


# Un ticket rouvert (de « en discussion » à « ouvert ») depuis la dernière
# mise à jour de sa carte : après « Réécrire », le nouveau brouillon.
_ROUVERT = (
    'EXISTS (SELECT 1 FROM ticket_events e WHERE e.ticket_id=p.ticket_id'
    " AND e.kind='transition.open'"
    " AND json_extract(e.payload_json, '$.from')='DISCUSSING'"
    ' AND e.ts>p.updated_at)'
)


def _nouvelle_version(
    conn: sqlite3.Connection, token: str, fil: str, ancienne: str, carte: dict
) -> str:
    """Poste la nouvelle version en bas du fil, avec une mention, et ôte
    ses boutons à l'ancienne carte ; rend l'id du nouveau message."""
    nouveau = send_message(token, fil, {**_mentions(conn), **carte})
    try:
        edit_message(
            token,
            fil,
            ancienne,
            {
                'content': 'Remplacée par la nouvelle version, plus bas.',
                'components': [],
            },
        )
    except DiscordError as exc:
        journal(f'ancienne carte du fil {fil} pas désactivée : {exc}')
    return str(nouveau.get('id') or ancienne)


def _mettre_a_jour(conn: sqlite3.Connection, token: str, now: str) -> int:
    """Met à jour la carte de chaque ticket qui a changé ; un ticket
    tranché voit son fil archivé. Un ticket rouvert (le nouveau brouillon
    après « Réécrire ») repart en bas du fil, avec une mention : les
    administrateurs sont prévenus qu'il attend un dernier clic. Rend le
    nombre de cartes mises à jour."""
    retry = (
        datetime.fromisoformat(now) - timedelta(minutes=RETRY_MINUTES)
    ).isoformat()
    count = 0
    for (
        ticket_id,
        fil,
        message,
        version,
        archive,
        state,
        rouvert,
    ) in conn.execute(
        f'SELECT p.ticket_id, p.thread_id, p.message_id, {VERSION},'
        f' p.archived, t.state, {_ROUVERT}'
        ' FROM ticket_posts p JOIN tickets t ON t.id=p.ticket_id'
        f" WHERE p.thread_id<>'' AND p.shown_state<>{VERSION}"
        ' AND (t.updated_at>p.updated_at OR p.updated_at<=?)',
        (retry,),
    ).fetchall():
        rendu = _carte(conn, str(ticket_id), now)
        if rendu is None:
            continue
        tranche = str(state) not in ('OPEN', 'DISCUSSING')
        carte_id = str(message or fil)
        try:
            # Un fil archivé se rouvre le temps de modifier sa carte.
            if archive:
                archive_thread(token, str(fil), False)
            if rouvert and not tranche:
                carte_id = _nouvelle_version(
                    conn, token, str(fil), carte_id, rendu[0]
                )
            else:
                edit_message(token, str(fil), carte_id, rendu[0])
            if tranche:
                archive_thread(token, str(fil), True)
            values = (str(version), int(tranche), carte_id)
        except DiscordError as exc:
            journal(f'carte du ticket {ticket_id} pas mise à jour : {exc}')
            values = (ECHEC_MODIF, int(archive), carte_id)
        conn.execute(
            'UPDATE ticket_posts SET shown_state=?, archived=?, message_id=?,'
            ' updated_at=? WHERE ticket_id=?',
            (*values, now, ticket_id),
        )
        conn.commit()
        count += values[0] != ECHEC_MODIF
    return count


def deliver(
    conn: sqlite3.Connection, token: str, now_iso: str | None = None
) -> int:
    """Ouvre les fils des tickets dus et met à jour les cartes des tickets
    qui ont changé. Rend le nombre de fils ouverts ou de cartes mises à
    jour ; rien sans forum réglé."""
    forum, depuis = forum_tickets(conn)
    if not forum:
        return 0
    moment = now_iso or utcnow()
    return _ouvrir_fils(conn, token, forum, depuis, moment) + _mettre_a_jour(
        conn, token, moment
    )
