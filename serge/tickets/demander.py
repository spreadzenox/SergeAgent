#!/usr/bin/env python3
"""Demander à Julien : un ticket qui fait attendre (décisions Q50 et Q85).

Le ticket porte sur une ligne (``ref_table``, ``ref_id``), par exemple un
envoi qui attend un humain. Son contenu suit son type en base : la liste
``contenu`` nomme des outils en base et les colonnes de cette ligne qu'ils
reçoivent ; ils sont lus dans cet ordre (exemple pour une conversation :
le business, le prospect, le fil, le brouillon). Puis viennent pourquoi
Serge demande et la question précise. Le code ne connaît aucun modèle de
ticket.

Un ticket encore ouvert sur la même ligne est mis à jour et rouvert, au
lieu d'en ouvrir un autre : après « Réécrire », le nouveau brouillon
revient dans le même ticket.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from typing import Any

from serge.horloge import iso_utc
from serge.interpreter.rules import safe_name
from serge.tickets.lifecycle import OPENISH, create_ticket, publish, reopen
from serge.tickets.shared import TicketError
from serge.tickets.types import ticket_types

# Ce qu'un bloc du ticket montre au plus, en caractères : la fin d'un bloc
# trop long est gardée (les derniers messages d'un fil).
BLOC_MAX = 3000


def _texte(result: dict[str, Any]) -> str:
    """Le résultat d'un outil en lignes lisibles, sans JSON."""
    rows = result.get('rows')
    if not isinstance(rows, list):
        return ''
    lignes = []
    for row in rows:
        if isinstance(row, dict):
            valeurs = [str(v) for v in row.values() if v not in ('', None)]
            lignes.append(' · '.join(valeurs))
    texte = '\n'.join(lignes)
    return texte if len(texte) <= BLOC_MAX else '…' + texte[-BLOC_MAX:]


# Exécute un outil en base : ``(outil, arguments)`` → son résultat. Le
# registre des outils (``serge/interpreter/tools.py``) le fournit.
Lanceur = Callable[[str, dict[str, Any]], dict[str, Any]]


def _contenu(
    spec: dict[str, Any], row: dict[str, Any], lancer: Lanceur
) -> dict[str, str]:
    """Les blocs du ticket, dans l'ordre de son type en base."""
    payload: dict[str, str] = {}
    for bloc in spec.get('contenu') or []:
        tool = str(bloc.get('tool') or '')
        args = {
            str(param): str(row.get(str(colonne), '') or '')
            for param, colonne in (bloc.get('params') or {}).items()
        }
        try:
            result = lancer(tool, args)
        except (ValueError, sqlite3.Error):
            result = {}
        payload[str(bloc.get('label') or tool)] = _texte(result) or '—'
    return payload


def demander(
    conn: sqlite3.Connection,
    lancer: Lanceur,
    ticket_type: str,
    ref_table: str,
    ref_id: str,
    raison: str,
    question: str = '',
    title: str = '',
) -> str:
    """Ouvre (ou rouvre) le ticket d'une ligne ; rend son id.

    Raises:
        TicketError: Type de ticket ou ligne inconnus.
    """
    spec = ticket_types(conn).get(ticket_type)
    if spec is None:
        raise TicketError(f'type de ticket inconnu : {ticket_type}')
    cursor = conn.execute(
        f'SELECT * FROM "{safe_name(ref_table)}" WHERE id=?', (ref_id,)
    )
    found = cursor.fetchone()
    if found is None:
        raise TicketError(f'ligne inconnue : {ref_table} {ref_id}')
    row = dict(zip([d[0] for d in cursor.description], found, strict=True))
    payload = {
        **_contenu(spec, row, lancer),
        'Pourquoi': raison,
        **({'La question': question} if question else {}),
    }
    texte = json.dumps(payload, ensure_ascii=False)
    holes = ','.join('?' * len(OPENISH))
    ouvert = conn.execute(
        f'SELECT id, state FROM tickets WHERE ref_table=? AND ref_id=?'
        f' AND state IN ({holes}) ORDER BY created_at DESC LIMIT 1',
        (ref_table, ref_id, *sorted(OPENISH)),
    ).fetchone()
    if ouvert is not None:
        conn.execute(
            'UPDATE tickets SET payload_json=?, question=?, updated_at=?'
            ' WHERE id=?',
            (texte, question, iso_utc(), ouvert[0]),
        )
        if str(ouvert[1]) == 'DISCUSSING':
            reopen(conn, str(ouvert[0]), actor='serge')
        return str(ouvert[0])
    ticket_id = create_ticket(
        conn,
        ticket_types(conn),
        ticket_type,
        title or raison[:120],
        payload,
        creator='serge',
    )
    conn.execute(
        'UPDATE tickets SET ref_table=?, ref_id=?, venture_id=?,'
        ' contact_id=?, question=? WHERE id=?',
        (
            ref_table,
            ref_id,
            str(row.get('venture_id') or ''),
            str(row.get('contact_id') or ''),
            question,
            ticket_id,
        ),
    )
    publish(conn, ticket_id)
    return ticket_id


def ask_owners(
    conn: sqlite3.Connection,
    args: dict[str, Any],
    inv: str,
    lancer: Lanceur,
) -> dict[str, Any]:
    """Capacité « Demander à Julien » : ``{ticket_type, ref_table, ref_id,
    raison, question, title}``."""
    try:
        ticket_id = demander(
            conn,
            lancer,
            str(args.get('ticket_type') or ''),
            str(args.get('ref_table') or ''),
            str(args.get('ref_id') or ''),
            str(args.get('raison') or '').strip() or f'demandé par {inv}',
            str(args.get('question') or '').strip(),
            str(args.get('title') or '').strip(),
        )
    except TicketError as exc:
        return {'ok': False, 'code': str(exc)}
    return {'ok': True, 'ticket_id': ticket_id}
