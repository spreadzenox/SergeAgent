#!/usr/bin/env python3
"""Fiches objet : une table / un enum = une brique cliquable."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.mc.libelles import (
    ETATS_CAMPAGNE,
    ETATS_FACTURE,
    ETATS_TICKET,
    ETATS_WORK,
    FUNNEL,
    LIFECYCLE,
    REGIMES,
    TYPES_TICKET,
    verbe,
)
from serge.mc.proj_outils import charge_json


def _row(conn: sqlite3.Connection, sql: str, args: tuple) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    return conn.execute(sql, args).fetchone()


def _champs(paires: list[tuple[str, Any]]) -> list[dict[str, str]]:
    return [{'k': k, 'v': '' if v is None else str(v)} for k, v in paires]


def _liens(items: list[tuple[str, str, str]]) -> list[dict[str, str]]:
    return [{'type': t, 'id': i, 'titre': titre} for t, i, titre in items]


def project_objet(conn: sqlite3.Connection, typ: str, ident: str) -> dict[str, Any] | None:
    """Fiche objet {type, id, titre, champs, enfants, preuve} ou None."""
    if typ == 'file':
        from serge.db.store import utcnow
        from serge.mc.proj_live import project_file_detail
        return project_file_detail(conn, utcnow())
    if typ in ('llm', 'llm_usage', 'contexte', 'ecoute', 'outil', 'notion'):
        from serge.mc.proj_llm import (
            project_contexte,
            project_ecoute,
            project_llm,
            project_llm_usage,
            project_notion,
            project_outil,
        )
        return {
            'llm': project_llm,
            'llm_usage': project_llm_usage,
            'contexte': project_contexte,
            'ecoute': project_ecoute,
            'outil': project_outil,
            'notion': project_notion,
        }[typ](conn, ident)
    if typ in ('sqlite', 'table'):
        from serge.mc.proj_sqlite import project_sqlite, project_table
        if typ == 'sqlite':
            return project_sqlite(conn, ident)
        return project_table(conn, ident)
    fn = {
        'venture': _venture,
        'campagne': _campagne,
        'prospect': _contact,
        'client': _contact,
        'facture': _facture,
        'abonnement': _abo,
        'compte': _compte,
        'plateforme': _plateforme,
        'ticket': _ticket,
        'lesson': _lesson,
        'playbook': _playbook,
        'work_item': _work,
        'touch': _touch,
        'inbound_event': _inbound,
        'listen_doc': _listen,
        'event': _event,
    }.get(typ)
    if fn is None:
        return None
    return fn(conn, ident)


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
                ('Où on en est', LIFECYCLE.get(row['lifecycle'], row['lifecycle'])),
                ('Serge peut avancer tout seul', 'oui' if row['schedulable'] else 'non'),
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
            + [
                ('touch', str(t[0]), f'{t[2]} · {t[1]}')
                for t in touches[:20]
            ]
        ),
        'preuve': row['thresholds_json'] or '',
    }


def _contact(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM contacts WHERE id=?', (ident,))
    if row is None:
        return None
    typ = 'client' if row['funnel_state'] == 'CUSTOMER' else 'prospect'
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
                ('Où il en est', FUNNEL.get(row['funnel_state'], row['funnel_state'])),
                ('Comment on s’est parlé', REGIMES.get(row['regime'], row['regime'])),
                ('E-mail', row['email']),
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


def _compte(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM accounts_standing WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'compte',
        'id': ident,
        'titre': f'{row["venue"]} · {row["handle"]}',
        'pourquoi': 'Un compte web de Serge. En pause = souvent pour ne pas se faire fermer.',
        'champs': _champs(
            [
                ('Plateforme', row['venue']),
                ('Identifiant', row['handle']),
                ('État', row['status']),
                ('Capital', row['capital']),
                ('Pause jusqu’à', row['cooldown_until'] or '—'),
            ]
        ),
        'enfants': _liens([('plateforme', row['venue'], row['venue'])]),
        'preuve': '',
    }


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
        'champs': _champs([('Portée', row['scope']), ('Si', row['conditions'])]),
        'enfants': [],
        'preuve': row['steps_json'] or '',
    }


def _work(conn: sqlite3.Connection, ident: str) -> dict | None:
    row = _row(conn, 'SELECT * FROM work_items WHERE id=?', (ident,))
    if row is None:
        return None
    return {
        'type': 'work_item',
        'id': ident,
        'titre': verbe(row['kind']),
        'pourquoi': 'Un tout petit travail (e-mail, classement…). La file est faite de ça.',
        'champs': _champs(
            [
                ('État', ETATS_WORK.get(row['status'], row['status'])),
                ('Essais', row['attempts']),
                ('Venture', row['venture_id'] or '—'),
                ('Contact', row['contact_id'] or '—'),
            ]
        ),
        'enfants': _liens(
            ([('venture', row['venture_id'], 'Venture')] if row['venture_id'] else [])
            + ([('ticket', row['ticket_id'], 'Ticket')] if row['ticket_id'] else [])
        ),
        'preuve': row['payload_json'] or '',
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
            ([('prospect', row['contact_id'], 'Personne')] if row['contact_id'] else [])
            + ([('campagne', row['campaign_id'], 'Campagne')] if row['campaign_id'] else [])
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
                    'flux RSS (Reddit, blogs…)' if row['source'] == 'rss' else row['source'],
                ),
                ('Adresse', row['url'] or '—'),
                ('Quand', row['fetched_at'] or '—'),
                ('Déjà mise dans un paquet ?', 'oui' if row['cluster_id'] else 'pas encore'),
            ]
        ),
        'enfants': _liens(
            [('ecoute', 'pages', 'Toutes les pages vraiment lues')]
            + (
                [
                    (
                        'plateforme',
                        row['source'],
                        'flux RSS' if row['source'] == 'rss' else row['source'],
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
