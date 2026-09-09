#!/usr/bin/env python3
"""Intents de facturation : ledger déterministe, prix jamais inventé.

draft → [quote_draft → quote_sent → quote_signed] → issued → sent →
paid | overdue | cancelled. Pas de prix → CollectError (le caller ouvre
un ticket QNA). Refund < seuil → auto + FYI ; ≥ seuil → ticket (caller).
Exécution rail (Stripe) séparée : ici = le ledger qui fait foi.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from collections.abc import Mapping
from typing import Any

from serge.db.store import append_event, utcnow

KINDS = frozenset({'invoice', 'payment_link', 'refund', 'canary'})


class CollectError(ValueError):
    pass


def _new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:12]}'


def _get(conn: sqlite3.Connection, intent_id: str) -> sqlite3.Row:
    row = conn.execute(
        'SELECT id, venture_id, kind, amount_eur, currency, intent_id,'
        ' doc_ref, status, receipt_json FROM transactions WHERE id=?',
        (intent_id,),
    ).fetchone()
    if not row:
        raise CollectError(f'intent inconnu : {intent_id}')
    return row


def _move(
    conn: sqlite3.Connection,
    intent_id: str,
    allowed_from: frozenset[str],
    to_status: str,
    extra: dict[str, Any] | None = None,
) -> None:
    row = _get(conn, intent_id)
    if row['status'] not in allowed_from:
        raise CollectError(
            f'{intent_id} : {row["status"]} → {to_status} interdit'
        )
    conn.execute(
        'UPDATE transactions SET status=?, updated_at=? WHERE id=?',
        (to_status, utcnow(), intent_id),
    )
    append_event(
        conn,
        actor='collect',
        type=f'collect.{to_status}',
        venture_id=row['venture_id'],
        payload={'id': intent_id, 'from': row['status'], **(extra or {})},
        links={'transaction': intent_id},
    )


def create_intent(
    conn: sqlite3.Connection,
    venture_id: str,
    kind: str,
    amount_eur: float,
    currency: str = 'EUR',
    requires_quote: bool = False,
    intent_key: str = '',
) -> str:
    """Crée un intent draft (prix owné exigé, jamais inventé).

    Raises:
        CollectError: Kind inconnu, montant <= 0 (→ ticket QNA caller).
    """
    if kind not in KINDS:
        raise CollectError(f'kind inconnu : {kind}')
    if amount_eur <= 0:
        raise CollectError('prix requis (jamais de défaut, ticket QNA)')
    row_id = _new_id('tx')
    moment = utcnow()
    conn.execute(
        'INSERT INTO transactions(id, venture_id, kind, amount_eur,'
        ' currency, intent_id, doc_ref, status, receipt_json, created_at,'
        ' updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (
            row_id,
            venture_id,
            kind,
            amount_eur,
            currency,
            intent_key or f'int_{uuid.uuid4().hex[:12]}',
            '',
            'draft',
            json.dumps({'requires_quote': requires_quote}),
            moment,
            moment,
        ),
    )
    append_event(
        conn,
        actor='collect',
        type='collect.draft',
        venture_id=venture_id,
        payload={'id': row_id, 'kind': kind, 'amount_eur': amount_eur},
        links={'transaction': row_id},
    )
    return row_id


def to_quote_draft(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(conn, intent_id, frozenset({'draft'}), 'quote_draft')


def to_quote_sent(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(conn, intent_id, frozenset({'quote_draft'}), 'quote_sent')


def to_quote_signed(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(conn, intent_id, frozenset({'quote_sent'}), 'quote_signed')


def to_issued(conn: sqlite3.Connection, intent_id: str, doc_ref: str) -> None:
    """Émet (facture numérotée OU PaymentLink). Réf exigée, jamais inventée.

    Raises:
        CollectError: Réf vide, ou devis requis non signé.
    """
    if not doc_ref.strip():
        raise CollectError('doc_ref requise (numérotation sans trou)')
    row = _get(conn, intent_id)
    envelope = json.loads(row['receipt_json'] or '{}')
    if envelope.get('requires_quote') and row['status'] != 'quote_signed':
        raise CollectError('devis signé requis avant émission')
    _move(
        conn,
        intent_id,
        frozenset({'draft', 'quote_signed'}),
        'issued',
        {'doc_ref': doc_ref},
    )
    conn.execute(
        'UPDATE transactions SET doc_ref=? WHERE id=?',
        (doc_ref, intent_id),
    )


def to_sent(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(conn, intent_id, frozenset({'issued'}), 'sent')


def mark_paid(
    conn: sqlite3.Connection,
    intent_id: str,
    receipt: dict[str, Any] | None = None,
) -> None:
    """Payé (webhook signé OU virement rapproché). Reçu fusionné."""
    _move(conn, intent_id, frozenset({'sent', 'issued'}), 'paid')
    row = _get(conn, intent_id)
    envelope = json.loads(row['receipt_json'] or '{}')
    envelope['receipt'] = receipt or {}
    conn.execute(
        'UPDATE transactions SET receipt_json=? WHERE id=?',
        (json.dumps(envelope, ensure_ascii=False), intent_id),
    )


def mark_overdue(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(conn, intent_id, frozenset({'sent'}), 'overdue')


def cancel(conn: sqlite3.Connection, intent_id: str) -> None:
    _move(
        conn,
        intent_id,
        frozenset(
            {
                'draft',
                'quote_draft',
                'quote_sent',
                'quote_signed',
                'issued',
                'sent',
                'overdue',
            }
        ),
        'cancelled',
    )


def create_canary(conn: sqlite3.Connection, venture_id: str, rail: str) -> str:
    """Canary 1 € owner→owner (marqué rail, exécuté séquence E)."""
    intent_id = create_intent(conn, venture_id, 'canary', 1.0)
    row = _get(conn, intent_id)
    envelope = json.loads(row['receipt_json'] or '{}')
    envelope['rail'] = rail
    envelope['canary'] = True
    conn.execute(
        'UPDATE transactions SET receipt_json=? WHERE id=?',
        (json.dumps(envelope, ensure_ascii=False), intent_id),
    )
    return intent_id


def request_refund(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    intent_id: str,
) -> dict[str, Any]:
    """Remboursement : < seuil → intent refund auto ; ≥ seuil → ticket.

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (collect.refund_auto_max_eur).
        intent_id: Transaction payée à rembourser.

    Returns:
        {auto: bool, refund_id: str|None} (caller: FYI ou ticket).
    """
    row = _get(conn, intent_id)
    if row['status'] != 'paid':
        raise CollectError('remboursement : transaction non payée')
    cap = float((policy.get('collect') or {}).get('refund_auto_max_eur', 5.0))
    if float(row['amount_eur']) < cap:
        refund_id = create_intent(
            conn,
            row['venture_id'],
            'refund',
            float(row['amount_eur']),
            str(row['currency'] or 'EUR'),
        )
        append_event(
            conn,
            actor='collect',
            type='collect.refund_auto',
            venture_id=row['venture_id'],
            payload={'id': refund_id, 'of': intent_id},
            links={'transaction': refund_id},
        )
        return {'auto': True, 'refund_id': refund_id}
    return {'auto': False, 'refund_id': None}
