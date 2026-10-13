#!/usr/bin/env python3
"""Le ticket d'un passage qui attend un clic (décision Q62).

Un lien réglé à la main note son passage et attend un feu vert : le
bouton « Passer à la suite » de Mission Control, ou le ticket « Passage »
envoyé à chaque administrateur. Le premier qui passe l'emporte ; le
ticket encore ouvert est alors annulé chez tous.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping

# Le type de ticket d'un passage qui attend un clic, et la table dont il
# parle : un passage se désigne par « lien:source » (décision Q62).
TICKET_PASSAGE = 'PASSAGE'
REF_PASSAGE = 'link_passages'


def ticket_de_passage(
    conn: sqlite3.Connection,
    link_id: str,
    source_ref: str,
    params: Mapping[str, str],
) -> None:
    """Un passage attend un clic : un ticket l'envoie aussi à chaque
    administrateur, à côté du bouton « Passer à la suite » de Mission
    Control (Q62). Le premier qui passe l'emporte."""
    from serge.tickets.lifecycle import create_ticket, publish
    from serge.tickets.types import ticket_types

    types = ticket_types(conn)
    if TICKET_PASSAGE not in types:
        return
    row = conn.execute(
        'SELECT title, from_invocation_id, to_invocation_id FROM links'
        ' WHERE id=?',
        (link_id,),
    ).fetchone()
    titre = str(row[0] or link_id) if row else link_id
    ticket_id = create_ticket(
        conn,
        types,
        TICKET_PASSAGE,
        f'Feu vert : {titre}',
        {
            'Le lien': f'{titre} ({row[1]} → {row[2]})' if row else titre,
            'Ce qui passe': ' · '.join(
                f'{k} = {v}' for k, v in sorted(params.items())
            )
            or '—',
        },
        creator='serge',
    )
    conn.execute(
        'UPDATE tickets SET ref_table=?, ref_id=? WHERE id=?',
        (REF_PASSAGE, f'{link_id}:{source_ref}', ticket_id),
    )
    publish(conn, ticket_id)


def clore_ticket_de_passage(
    conn: sqlite3.Connection, link_id: str, source_ref: str
) -> None:
    """Le passage est parti (par Mission Control ou par son ticket) : son
    ticket encore ouvert est annulé chez tous."""
    from serge.tickets.lifecycle import OPENISH, cancel

    holes = ','.join('?' * len(OPENISH))
    for (ticket_id,) in conn.execute(
        f'SELECT id FROM tickets WHERE ref_table=? AND ref_id=?'
        f' AND state IN ({holes})',
        (REF_PASSAGE, f'{link_id}:{source_ref}', *sorted(OPENISH)),
    ).fetchall():
        cancel(conn, str(ticket_id), 'passage déjà parti')
