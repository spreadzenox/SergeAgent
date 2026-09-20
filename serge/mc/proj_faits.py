#!/usr/bin/env python3
"""Fiches occurrences : venture, campagne, contact, caisse."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.funnels.contacts import (
    contact_reference_value,
    load_contact_references,
)
from serge.mc.libelles import (
    ETATS_CAMPAGNE,
    ETATS_FACTURE,
    FUNNEL,
    LIFECYCLE,
    REGIMES,
)
from serge.mc.proj_objet_base import _champs, _liens, _row


def _venture(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM ventures WHERE id=?', (ident,))
    if row is None:
        return None
    camps = conn.execute(
        'SELECT id, channel, state FROM campaigns WHERE venture_id=?',
        (ident,),
    ).fetchall()
    people = conn.execute(
        'SELECT id, display, funnel_state FROM contacts WHERE venture_id=?',
        (ident,),
    ).fetchall()
    txs = conn.execute(
        'SELECT id, amount_eur, status FROM transactions WHERE venture_id=?',
        (ident,),
    ).fetchall()
    enfants = _liens(
        [
            (
                'campagne',
                str(c[0]),
                f'{c[1]} · {ETATS_CAMPAGNE.get(c[2], c[2])}',
            )
            for c in camps
        ]
        + [
            (
                'client' if p[2] == 'CUSTOMER' else 'prospect',
                str(p[0]),
                f'{p[1] or p[0]} · {FUNNEL.get(p[2], p[2])}',
            )
            for p in people
        ]
        + [
            (
                'facture',
                str(t[0]),
                f'{t[1]} € · {ETATS_FACTURE.get(t[2], t[2])}',
            )
            for t in txs
        ]
    )
    return {
        'type': 'venture',
        'id': ident,
        'titre': row['name'] or ident,
        'pourquoi': 'Une idée de business que Serge essaie — une seule à la fois.',
        'champs': _champs(
            [
                (
                    'Où on en est',
                    LIFECYCLE.get(row['lifecycle'], row['lifecycle']),
                ),
                (
                    'Serge peut avancer tout seul',
                    'oui' if row['schedulable'] else 'non',
                ),
            ]
        ),
        'enfants': enfants,
        'preuve': '',
    }


def _campagne(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM campaigns WHERE id=?', (ident,))
    if row is None:
        return None
    touches = conn.execute(
        'SELECT id, status, channel FROM touches WHERE campaign_id=?',
        (ident,),
    ).fetchall()
    return {
        'type': 'campagne',
        'id': ident,
        'titre': f'Essai {row["channel"]} ({row["family"]})',
        'pourquoi': 'Un essai concret : on parle à des gens, par un canal, et on mesure.',
        'champs': _champs(
            [
                ('État', ETATS_CAMPAGNE.get(row['state'], row['state'])),
                ('Personnes visées', row['n_target']),
                ('Idée de business', row['venture_id']),
            ]
        ),
        'enfants': _liens(
            [('venture', row['venture_id'], 'Venture')]
            + [('touch', str(t[0]), f'{t[2]} · {t[1]}') for t in touches[:20]]
        ),
        'preuve': row['thresholds_json'] or '',
    }


def _contact(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM contacts WHERE id=?', (ident,))
    if row is None:
        return None
    typ = 'client' if row['funnel_state'] == 'CUSTOMER' else 'prospect'
    references = load_contact_references(row['contact_reference_by_canal'])
    trace_channel = next(
        (
            channel
            for channel, reference in references.items()
            if reference.get('handle') or reference.get('profile_url')
        ),
        '',
    )
    trace = references.get(trace_channel, {})
    return {
        'type': typ,
        'id': ident,
        'titre': row['display'] or ident,
        'pourquoi': (
            'Un client a déjà payé. Tout le reste de son histoire reste là.'
            if typ == 'client'
            else 'Quelqu’un de contacté, pas encore payé. On voit où il en est.'
        ),
        'champs': _champs(
            [
                (
                    'Où il en est',
                    FUNNEL.get(row['funnel_state'], row['funnel_state']),
                ),
                (
                    'Comment on s’est parlé',
                    REGIMES.get(row['regime'], row['regime']),
                ),
                ('E-mail', contact_reference_value(row, 'email')),
                ('Lieu', trace.get('venue') or trace_channel or '—'),
                ('Sur ce lieu', trace.get('handle') or '—'),
                ('Profil', trace.get('profile_url') or '—'),
                ('Idée de business', row['venture_id']),
            ]
        ),
        'enfants': _liens([('venture', row['venture_id'], 'Venture')]),
        'preuve': '',
    }


def _facture(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM transactions WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'facture',
        'id': ident,
        'titre': f'{row["amount_eur"]} € · {ETATS_FACTURE.get(row["status"], row["status"])}',
        'pourquoi': 'L’argent qui est vraiment passé, ou qui est en train.',
        'champs': _champs(
            [
                ('Montant', f'{row["amount_eur"]} {row["currency"]}'),
                ('État', ETATS_FACTURE.get(row['status'], row['status'])),
                ('Référence', row['intent_id']),
                ('Idée de business', row['venture_id']),
            ]
        ),
        'enfants': _liens([('venture', row['venture_id'], 'Venture')]),
        'preuve': row['receipt_json'] or '',
    }


def _abo(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM subscriptions WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'abonnement',
        'id': ident,
        'titre': f'{row["amount_eur"]} € / {row["period"]}',
        'pourquoi': 'Un paiement qui revient tout seul (chaque mois, par exemple).',
        'champs': _champs(
            [
                ('État', row['status']),
                ('Via', row['provider']),
                ('Idée de business', row['venture_id']),
            ]
        ),
        'enfants': _liens([('venture', row['venture_id'], 'Venture')]),
        'preuve': '',
    }


def _fiche_compte(conn: sqlite3.Connection, ident: str) -> dict | None:
    from serge.mc.proj_compte import project_compte

    return project_compte(conn, ident)


def _plateforme(conn: sqlite3.Connection, ident: str) -> dict | None:
    comptes = conn.execute(
        'SELECT id, handle, status FROM accounts_standing WHERE venue=?',
        (ident,),
    ).fetchall()
    docs = conn.execute(
        'SELECT id, title FROM listen_docs WHERE source=? LIMIT 12',
        (ident,),
    ).fetchall()
    camps = conn.execute(
        'SELECT id, state FROM campaigns WHERE channel=?', (ident,)
    ).fetchall()
    if not comptes and not docs and not camps:
        return None
    return {
        'type': 'plateforme',
        'id': ident,
        'titre': ident,
        'pourquoi': 'Un endroit du web : compte, essai, ou pages lues (Reddit, e-mail…).',
        'champs': _champs(
            [
                ('Comptes', len(comptes)),
                ('Pages lues', len(docs)),
                ('Essais', len(camps)),
            ]
        ),
        'enfants': _liens(
            [('compte', str(c[0]), str(c[1])) for c in comptes]
            + [('listen_doc', str(d[0]), d[1] or d[0]) for d in docs]
            + [('campagne', str(c[0]), str(c[1])) for c in camps]
        ),
        'preuve': '',
    }


def project_fait_pipe(
    conn: sqlite3.Connection, typ: str, ident: str
) -> dict[str, Any] | None:
    """Venture / campagne / contact / caisse / compte."""
    fn = {
        'venture': _venture,
        'campagne': _campagne,
        'prospect': _contact,
        'client': _contact,
        'facture': _facture,
        'abonnement': _abo,
        'compte': _fiche_compte,
        'plateforme': _plateforme,
    }.get(typ)
    return None if fn is None else fn(conn, ident)
