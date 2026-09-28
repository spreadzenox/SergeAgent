#!/usr/bin/env python3
"""Fiches occurrences : ticket, file, touches, pages lues."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.mc.libelles import (
    ETATS_TICKET,
    TYPES_TICKET,
    verbe,
)
from serge.mc.proj_objet_base import _champs, _liens, _row
from serge.mc.proj_outils import charge_json

# Les étiquettes de tri d'une page (étape 1).
ETIQUETTES = {
    '': 'pas encore triée',
    'besoin_nouveau': 'besoin nouveau',
    'bruit': 'bruit',
    'enrichit': 'enrichit un business existant',
    'preuve': 'preuve d’un business',
}


def _ticket(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM tickets WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'ticket',
        'id': ident,
        'titre': row['title'],
        'pourquoi': 'Une question pour toi. Serge attend. Même chose que sur Discord.',
        'champs': _champs(
            [
                ('Type', TYPES_TICKET.get(row['type'], row['type'])),
                ('État', ETATS_TICKET.get(row['state'], row['state'])),
                ('Échéance', row['expiry_at'] or '—'),
            ]
        ),
        'enfants': [],
        'preuve': row['payload_json'] or '',
    }


def _lesson(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM lessons WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'lesson',
        'id': ident,
        'titre': row['statement'][:80],
        'pourquoi': 'Quelque chose qu’on a appris et qu’on retient pour la suite.',
        'champs': _champs(
            [
                ('Confiance', row['confidence']),
                ('Portée', row['scope']),
                ('État', row['status']),
            ]
        ),
        'enfants': [],
        'preuve': row['sources_json'] or '',
    }


def _playbook(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM playbooks WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'playbook',
        'id': ident,
        'titre': row['name'],
        'pourquoi': 'Une recette déjà écrite : si ça arrive, fais ces étapes.',
        'champs': _champs(
            [('Portée', row['scope']), ('Si', row['conditions'])]
        ),
        'enfants': [],
        'preuve': row['steps_json'] or '',
    }


def _touch(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM touches WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'touch',
        'id': ident,
        'titre': f'{row["channel"]} · {row["status"]}',
        'pourquoi': 'Une fois où on a parlé à quelqu’un (e-mail, appel…).',
        'champs': _champs(
            [
                ('Canal', row['channel']),
                ('État', row['status']),
                ('Coût', f'{row["cost_eur"]} €'),
            ]
        ),
        'enfants': _liens(
            [('campagne', row['campaign_id'], 'Campagne')]
            + (
                [('prospect', row['contact_id'], 'Personne')]
                if row['contact_id']
                else []
            )
        ),
        'preuve': '',
    }


def _inbound(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM inbound_events WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'inbound_event',
        'id': ident,
        'titre': row['signal'] or row['native_type'],
        'pourquoi': 'Quelqu’un a répondu. On range le message avant de décider.',
        'champs': _champs(
            [
                ('Classe', row['class'] or '—'),
                ('Score', row['score']),
                ('Canal', row['channel']),
            ]
        ),
        'enfants': _liens(
            (
                [('prospect', row['contact_id'], 'Personne')]
                if row['contact_id']
                else []
            )
            + (
                [('campagne', row['campaign_id'], 'Campagne')]
                if row['campaign_id']
                else []
            )
        ),
        'preuve': row['payload_json'] or '',
    }


def _listen(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM listen_docs WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'listen_doc',
        'id': ident,
        'titre': row['title'] or ident,
        'pourquoi': 'Une page vraiment lue. Matière première d’une idée de business.',
        'champs': _champs(
            [
                (
                    'D’où ça vient',
                    'flux RSS (Reddit, blogs…)'
                    if row['source'] == 'rss'
                    else row['source'],
                ),
                ('Adresse', row['url'] or '—'),
                ('Quand', row['fetched_at'] or '—'),
                (
                    'Étiquette de tri',
                    ETIQUETTES.get(str(row['label']), str(row['label'])),
                ),
                ('Cycle', row['cycle_id'] or '—'),
            ]
        ),
        'enfants': _liens(
            [('ecoute', 'pages', 'Toutes les pages vraiment lues')]
            + (
                [
                    (
                        'plateforme',
                        row['source'],
                        'flux RSS'
                        if row['source'] == 'rss'
                        else row['source'],
                    )
                ]
                if row['source']
                else []
            )
        ),
        'preuve': row['excerpt'] or '',
    }


def _event(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM events WHERE id=?', (ident,))
    if row is None:
        return None
    payload = charge_json(row['payload_json'])
    return {
        'type': 'event',
        'id': ident,
        'titre': verbe(row['type']),
        'pourquoi': 'Un fait enregistré, dans l’ordre. On n’efface pas : on ajoute.',
        'champs': _champs([('Acteur', row['actor']), ('Quand', row['ts'])]),
        'enfants': [],
        'preuve': json.dumps(payload, ensure_ascii=False, indent=2),
    }


def project_fait_trace(
    conn: sqlite3.Connection, typ: str, ident: str
) -> dict[str, Any] | None:
    """Ticket, file, touche, inbound, page, event."""
    fn = {
        'ticket': _ticket,
        'lesson': _lesson,
        'playbook': _playbook,
        'touch': _touch,
        'inbound_event': _inbound,
        'listen_doc': _listen,
        'event': _event,
    }.get(typ)
    return None if fn is None else fn(conn, ident)
