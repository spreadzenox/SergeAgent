#!/usr/bin/env python3
"""Abonnements Stripe : table ``subscriptions`` reliée aux transactions."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from serge.collect.intents import (
    CollectError,
    create_intent,
    mark_paid,
    to_issued,
)
from serge.db.store import utcnow

VENTURE = 'serge-collect-stripe'
STATUTS = frozenset(
    {
        'active',
        'past_due',
        'canceled',
        'unpaid',
        'trialing',
        'incomplete',
        'incomplete_expired',
        'paused',
    }
)


def assurer_colonnes(conn: sqlite3.Connection) -> None:
    """Ajoute ``last_transaction_id`` si la table existe déjà sans."""
    cols = {
        str(row[1]) for row in conn.execute('PRAGMA table_info(subscriptions)')
    }
    if cols and 'last_transaction_id' not in cols:
        conn.execute(
            'ALTER TABLE subscriptions ADD COLUMN last_transaction_id'
            " TEXT NOT NULL DEFAULT ''"
        )


def _inner(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get('data') if isinstance(event.get('data'), dict) else {}
    obj = data.get('object') if isinstance(data, dict) else {}
    return obj if isinstance(obj, dict) else {}


def _euros_depuis_centimes(raw: object) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return 0.0
    try:
        return round(int(raw) / 100, 2)
    except (TypeError, ValueError):
        return 0.0


def _montant_sub(obj: dict[str, Any]) -> float:
    items = obj.get('items')
    if not isinstance(items, dict):
        return 0.0
    data = items.get('data')
    if not isinstance(data, list) or not data:
        return 0.0
    first = data[0]
    if not isinstance(first, dict):
        return 0.0
    price = first.get('price')
    if not isinstance(price, dict):
        return 0.0
    return _euros_depuis_centimes(price.get('unit_amount'))


def _renews(obj: dict[str, Any]) -> str:
    raw = obj.get('current_period_end')
    if not isinstance(raw, (int, float, str)) or isinstance(raw, bool):
        return ''
    try:
        return datetime.fromtimestamp(int(raw), UTC).isoformat()
    except (TypeError, ValueError, OSError):
        return ''


def upsert_abonnement(
    conn: sqlite3.Connection,
    obj: dict[str, Any],
    *,
    last_tx: str = '',
) -> dict[str, Any]:
    """Crée ou met à jour un abonnement depuis l’objet Stripe.

    Args:
        conn: Canon.
        obj: Objet ``subscription`` Stripe.
        last_tx: Id transaction liée (facture encaissée).

    Returns:
        ``{id, status}``.
    """
    assurer_colonnes(conn)
    external = str(obj.get('id') or '')
    if not external.startswith('sub_'):
        return {'id': '', 'status': 'ignored'}
    statut = str(obj.get('status') or 'active')
    if statut not in STATUTS:
        statut = 'active'
    moment = utcnow()
    row = conn.execute(
        'SELECT id FROM subscriptions WHERE external_id=?', (external,)
    ).fetchone()
    ident = str(row[0]) if row else f'abo_{external[4:16]}'
    montant = _montant_sub(obj)
    renews = _renews(obj)
    if row is None:
        conn.execute(
            'INSERT INTO subscriptions(id, venture_id, provider, external_id,'
            ' amount_eur, currency, period, status, renews_at,'
            ' last_transaction_id, created_at, updated_at)'
            ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
            (
                ident,
                VENTURE,
                'stripe',
                external,
                montant,
                'EUR',
                'monthly',
                statut,
                renews,
                last_tx,
                moment,
                moment,
            ),
        )
    else:
        conn.execute(
            'UPDATE subscriptions SET status=?, updated_at=?,'
            ' amount_eur=CASE WHEN ?>0 THEN ? ELSE amount_eur END,'
            " renews_at=CASE WHEN ?!='' THEN ? ELSE renews_at END,"
            " last_transaction_id=CASE WHEN ?!='' THEN ? ELSE"
            ' last_transaction_id END WHERE id=?',
            (
                statut,
                moment,
                montant,
                montant,
                renews,
                renews,
                last_tx,
                last_tx,
                ident,
            ),
        )
    return {'id': ident, 'statut_abo': statut}


def appliquer_facture_abo(
    conn: sqlite3.Connection, obj: dict[str, Any]
) -> dict[str, Any]:
    """Lie ``invoice.paid`` : transaction + abonnement.

    Args:
        conn: Canon.
        obj: Objet ``invoice`` Stripe.

    Returns:
        Statut fermé.
    """
    sub_id = str(obj.get('subscription') or '')
    pi_id = str(obj.get('payment_intent') or '')
    euros = _euros_depuis_centimes(obj.get('amount_paid'))
    if euros <= 0:
        return {'status': 'ignored', 'reason': 'montant'}
    tx_id = ''
    if pi_id.startswith('pi_'):
        row = conn.execute(
            'SELECT id, status FROM transactions WHERE intent_id=?',
            (pi_id,),
        ).fetchone()
        if row is None:
            try:
                tx_id = create_intent(
                    conn,
                    VENTURE,
                    'invoice',
                    euros,
                    intent_key=pi_id,
                )
                to_issued(conn, tx_id, str(obj.get('id') or pi_id))
                mark_paid(
                    conn,
                    tx_id,
                    {'stripe_invoice': str(obj.get('id') or '')},
                )
            except CollectError as exc:
                return {'status': 'refused', 'error': str(exc)}
        else:
            tx_id = str(row[0])
            if str(row[1]) != 'paid':
                try:
                    mark_paid(
                        conn,
                        tx_id,
                        {'stripe_invoice': str(obj.get('id') or '')},
                    )
                except CollectError as exc:
                    return {'status': 'refused', 'error': str(exc)}
    if sub_id.startswith('sub_'):
        upsert_abonnement(
            conn, {'id': sub_id, 'status': 'active'}, last_tx=tx_id
        )
    return {'status': 'ok', 'id': tx_id, 'subscription': sub_id}


def appliquer_event_abo(
    conn: sqlite3.Connection, event: dict[str, Any]
) -> dict[str, Any] | None:
    """Route un événement Stripe abo, ou None si ce n’est pas le sujet.

    Args:
        conn: Canon.
        event: Événement authentifié.

    Returns:
        Résultat ou None (laisser le handler paiements one-shot).
    """
    kind = str(event.get('type') or '')
    obj = _inner(event)
    if kind.startswith('customer.subscription.'):
        etat = upsert_abonnement(conn, obj)
        if not etat['id']:
            return {'status': 'ignored', 'type': kind}
        return {
            'status': 'ok',
            'id': etat['id'],
            'abonnement': etat['statut_abo'],
        }
    if kind == 'invoice.paid':
        return appliquer_facture_abo(conn, obj)
    return None
