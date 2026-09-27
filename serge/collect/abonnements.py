#!/usr/bin/env python3
"""Abonnements Stripe : table ``subscriptions`` reliée aux transactions.

Chaque abonnement est rattaché à son business. Serge écrit l'identifiant
du business dans le champ ``metadata.venture_id`` du prix Stripe (ou de
l'abonnement) ; Stripe le renvoie dans chaque événement. Exemple :
``{'metadata': {'venture_id': 'v1'}}`` → l'abonnement va au business ``v1``.

Sans identifiant, ou avec un business inconnu, l'abonnement est gardé sans
business et un événement ``collect.subscription_unattached`` est écrit au
journal à sa création.
"""

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
from serge.db.store import append_event, utcnow

CLE_BUSINESS = 'venture_id'
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


def _inner(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get('data') if isinstance(event.get('data'), dict) else {}
    obj = data.get('object') if isinstance(data, dict) else {}
    return obj if isinstance(obj, dict) else {}


def _premier(liste: object) -> dict[str, Any]:
    """Premier élément de ``{'data': [...]}``, ou ``{}``."""
    data = liste.get('data') if isinstance(liste, dict) else None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0]
    return {}


def _venture_lue(*objets: object) -> str:
    """Premier ``metadata.venture_id`` trouvé dans ces objets Stripe."""
    for objet in objets:
        if not isinstance(objet, dict):
            continue
        metadata = objet.get('metadata')
        if isinstance(metadata, dict):
            valeur = str(metadata.get(CLE_BUSINESS) or '').strip()
            if valeur:
                return valeur
    return ''


def venture_de_l_abonnement(obj: dict[str, Any]) -> str:
    """Business inscrit sur l'abonnement, son prix ou son plan."""
    ligne = _premier(obj.get('items'))
    return _venture_lue(obj, ligne.get('price'), ligne.get('plan'))


def venture_de_la_facture(obj: dict[str, Any]) -> str:
    """Business inscrit sur la facture, son abonnement ou son prix."""
    ligne = _premier(obj.get('lines'))
    return _venture_lue(
        obj.get('subscription_details'),
        obj,
        ligne.get('price'),
        ligne,
    )


def _venture_connue(conn: sqlite3.Connection, venture_id: str) -> str:
    if (
        venture_id
        and conn.execute(
            'SELECT 1 FROM ventures WHERE id=?', (venture_id,)
        ).fetchone()
    ):
        return venture_id
    return ''


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
    venture_id: str = '',
) -> dict[str, Any]:
    """Crée ou met à jour un abonnement depuis l’objet Stripe.

    Un business déjà rattaché n'est jamais remplacé.

    Args:
        conn: Canon.
        obj: Objet ``subscription`` Stripe.
        last_tx: Id transaction liée (facture encaissée).
        venture_id: Business lu ailleurs (facture), si l'objet n'en dit rien.

    Returns:
        ``{id, statut_abo, venture_id}``.
    """
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
    venture = _venture_connue(conn, venture_de_l_abonnement(obj) or venture_id)
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
                venture,
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
            ' last_transaction_id END,'
            " venture_id=CASE WHEN venture_id='' THEN ? ELSE venture_id END"
            ' WHERE id=?',
            (
                statut,
                moment,
                montant,
                montant,
                renews,
                renews,
                last_tx,
                last_tx,
                venture,
                ident,
            ),
        )
    final = conn.execute(
        'SELECT venture_id FROM subscriptions WHERE id=?', (ident,)
    ).fetchone()
    rattache = str(final[0]) if final else ''
    if not rattache and row is None:
        append_event(
            conn,
            actor='collect.stripe',
            type='collect.subscription_unattached',
            payload={'subscription': external},
        )
    return {'id': ident, 'statut_abo': statut, 'venture_id': rattache}


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
    venture = _venture_connue(conn, venture_de_la_facture(obj))
    if not venture and sub_id:
        row = conn.execute(
            'SELECT venture_id FROM subscriptions WHERE external_id=?',
            (sub_id,),
        ).fetchone()
        venture = str(row[0]) if row else ''
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
                    venture,
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
            conn,
            {'id': sub_id, 'status': 'active'},
            last_tx=tx_id,
            venture_id=venture,
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
