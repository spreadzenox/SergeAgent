#!/usr/bin/env python3
"""URL et application des webhooks Stripe (domaine d’instance, pas en dur)."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.collect.intents import CollectError, mark_paid
from serge.collect.rails import RailError, parse_stripe_webhook

STRIPE_WEBHOOK_PATH = '/hooks/stripe'
STRIPE_RECEIVER_UPSTREAM = '127.0.0.1:8788'
STRIPE_VENTURE_ID = 'serge-collect-stripe'
HANDLED_TYPES = frozenset(
    {'payment_intent.succeeded', 'checkout.session.completed'}
)


def public_webhook_url(public_hostname: str) -> str:
    """URL HTTPS à coller dans le dashboard Stripe (même hôte que le MC).

    Args:
        public_hostname: Hôte d’instance (avec ou sans schéma).

    Returns:
        `https://<hôte>/hooks/stripe`.

    Raises:
        ValueError: Hostname vide après normalisation.
    """
    host = public_hostname.strip().lower().rstrip('/')
    if host.startswith('https://') or host.startswith('http://'):
        host = host.split('://', 1)[1]
    host = host.split('/', 1)[0]
    if not host:
        raise ValueError('public_hostname manquant')
    return f'https://{host}{STRIPE_WEBHOOK_PATH}'


def installer_hint(public_hostname: str) -> str:
    """Texte wizard : où coller l’URL avant de saisir les whsec.

    Args:
        public_hostname: Hôte déjà choisi (vide → placeholder).

    Returns:
        Bloc à afficher avant la saisie des `whsec`.
    """
    try:
        url = public_webhook_url(public_hostname)
    except ValueError:
        url = f'https://<domaine>{STRIPE_WEBHOOK_PATH}'
    return (
        'Webhook Stripe — Dashboard → Developers → Webhooks\n'
        f'  URL (mode test ET mode live) : {url}\n'
        '  Événements : payment_intent.succeeded, '
        'checkout.session.completed'
    )


def payment_intent_id(event: dict[str, Any]) -> str:
    """Extrait le `pi_` depuis un événement Stripe déjà vérifié.

    Args:
        event: Objet événement Stripe (type + data.object).

    Returns:
        Identifiant `pi_…` ou chaîne vide.
    """
    kind = str(event.get('type') or '')
    obj = event.get('data') if isinstance(event.get('data'), dict) else {}
    inner = obj.get('object') if isinstance(obj, dict) else {}
    if not isinstance(inner, dict):
        return ''
    if kind == 'payment_intent.succeeded':
        return str(inner.get('id') or '')
    if kind == 'checkout.session.completed':
        return str(inner.get('payment_intent') or '')
    return ''


def verify_event(
    raw_body: bytes,
    sig_header: str,
    secrets: dict[str, str],
    now: float | None = None,
) -> tuple[str, dict[str, Any]]:
    """Essaie live puis test. Retourne (mode, événement).

    Args:
        raw_body: Corps brut du POST.
        sig_header: En-tête `Stripe-Signature`.
        secrets: `whsec` indexés par `live` / `test`.
        now: Horodatage (tests) ; défaut = maintenant.

    Returns:
        Couple (mode, événement parsé).

    Raises:
        RailError: HMAC invalide, secret manquant, ou webhook périmé.
    """
    last = RailError('SIGNATURE: secret webhook manquant')
    for mode in ('live', 'test'):
        secret = str(secrets.get(mode) or '').strip()
        if not secret:
            continue
        try:
            return mode, parse_stripe_webhook(
                raw_body, sig_header, secret, now
            )
        except RailError as exc:
            last = exc
            if str(exc).startswith('STALE'):
                raise
    raise last


def apply_event(
    conn: sqlite3.Connection, event: dict[str, Any]
) -> dict[str, Any]:
    """Passe la transaction en paid si un intent_id correspond au pi_.

    Args:
        conn: Canon SQLite.
        event: Événement déjà authentifié.

    Returns:
        Statut fermé : `ok` / `already` / `ignored` / `unmatched` / `refused`.
    """
    kind = str(event.get('type') or '')
    if kind not in HANDLED_TYPES:
        return {'status': 'ignored', 'type': kind}
    pi_id = payment_intent_id(event)
    if not pi_id.startswith('pi_'):
        return {'status': 'ignored', 'type': kind, 'reason': 'no_pi'}
    row = conn.execute(
        'SELECT id, status FROM transactions WHERE intent_id=?',
        (pi_id,),
    ).fetchone()
    if row is None:
        return {'status': 'unmatched', 'payment_intent': pi_id}
    tx_id = str(row['id'])
    if str(row['status']) == 'paid':
        return {'status': 'ok', 'already': True, 'id': tx_id}
    receipt = {
        'stripe_event': str(event.get('id') or ''),
        'payment_intent': pi_id,
    }
    try:
        mark_paid(conn, tx_id, receipt)
    except CollectError as exc:
        return {'status': 'refused', 'id': tx_id, 'error': str(exc)}
    return {'status': 'ok', 'id': tx_id, 'payment_intent': pi_id}
