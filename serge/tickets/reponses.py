#!/usr/bin/env python3
"""Une réponse à un ticket réveille le pipeline (décision Q85).

Chaque réponse (un bouton sur Discord ou dans Mission Control, un texte
saisi, ou la décision par défaut à l'expiration) est une ligne de
``ticket_answers``, avec ce dont parle le ticket. Les déclencheurs « une
ligne est écrite » de cette table, réglés en base, réveillent les
invocations qui doivent réagir : par exemple, « Envoyer le brouillon »
relance l'envoi qui attendait. Le code ne connaît aucune de ces
invocations.
"""

from __future__ import annotations

import sqlite3

from serge.horloge import iso_utc
from serge.interpreter.rules import safe_name
from serge.tickets.shared import new_id


def message_du_ticket(
    conn: sqlite3.Connection, ticket_id: str
) -> dict[str, str]:
    """Le message dont parle un ticket : ``{texte, objet}``, ou ``{}``.

    Un ticket porte sur un message quand sa ligne a un texte (``body``),
    par exemple un envoi qui attend un humain. « Ma réponse » s'ouvre avec
    ce texte et cet objet, à modifier.
    """
    ref = conn.execute(
        'SELECT ref_table, ref_id FROM tickets WHERE id=?', (ticket_id,)
    ).fetchone()
    if ref is None or not ref[0]:
        return {}
    cursor = conn.execute(
        f'SELECT * FROM "{safe_name(str(ref[0]))}" WHERE id=?', (ref[1],)
    )
    found = cursor.fetchone()
    if found is None:
        return {}
    ligne = dict(zip([d[0] for d in cursor.description], found, strict=True))
    if 'body' not in ligne:
        return {}
    return {
        'texte': str(ligne.get('body') or ''),
        'objet': str(ligne.get('subject') or ''),
    }


def noter_reponse(
    conn: sqlite3.Connection,
    ticket_id: str,
    acte: str,
    texte: str,
    par: str,
    objet: str = '',
) -> str:
    """Écrit la réponse et réveille ses déclencheurs ; rend son id.

    Args:
        ticket_id: Le ticket.
        acte: Le bouton (``envoyer_brouillon``…), ou la décision par défaut
            du type de ticket pour une expiration.
        texte: Le texte saisi (une réponse, des consignes), ou ``''``.
        par: Qui a répondu (``discord:<id>``, ``owner``, ``serge``).
        objet: L'objet saisi avec le texte (une réponse par e-mail) ; vide,
            celui du message dont parle le ticket est gardé.
    """
    from serge.interpreter.flow import notify_rows_written

    row = conn.execute(
        'SELECT type, ref_table, ref_id, venture_id, contact_id, question'
        ' FROM tickets WHERE id=?',
        (ticket_id,),
    ).fetchone()
    if row is None:
        return ''
    ident = new_id('ta')
    kind, ref_table, ref_id, venture, contact, question = map(str, row)
    objet = objet.strip() or message_du_ticket(conn, ticket_id).get(
        'objet', ''
    )
    conn.execute(
        'INSERT INTO ticket_answers(id, ticket_id, ticket_type, acte, text,'
        ' subject, answered_by, ref_table, ref_id, venture_id, contact_id,'
        ' question, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            ident,
            ticket_id,
            kind,
            acte,
            texte,
            objet,
            par,
            ref_table,
            ref_id,
            venture,
            contact,
            question,
            iso_utc(),
        ),
    )
    notify_rows_written(conn, 'ticket_answers', [ident])
    return ident
