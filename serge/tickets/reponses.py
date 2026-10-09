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
from serge.tickets.shared import new_id


def noter_reponse(
    conn: sqlite3.Connection,
    ticket_id: str,
    acte: str,
    texte: str,
    par: str,
) -> str:
    """Écrit la réponse et réveille ses déclencheurs ; rend son id.

    Args:
        ticket_id: Le ticket.
        acte: Le bouton (``envoyer_brouillon``…), ou la décision par défaut
            du type de ticket pour une expiration.
        texte: Le texte saisi (une réponse, des consignes), ou ``''``.
        par: Qui a répondu (``discord:<id>``, ``owner``, ``serge``).
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
    conn.execute(
        'INSERT INTO ticket_answers(id, ticket_id, ticket_type, acte, text,'
        ' answered_by, ref_table, ref_id, venture_id, contact_id, question,'
        ' created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
        (
            ident,
            ticket_id,
            kind,
            acte,
            texte,
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
