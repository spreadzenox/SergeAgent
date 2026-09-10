#!/usr/bin/env python3
"""Rail Stripe : PaymentIntents + refunds + webhooks vérifiés. Test-first.

Mode test par défaut (clé sk_test_ exigée, live refusée). Idempotence
native Stripe (Idempotency-Key). Erreurs typées routables (RailError).
urllib only, pas de dépendance. PaymentLinks/factures avec les flux
clients (phase 2) — ici le minimum canary.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from serge.paths import config_root
from serge.secrets import read_secret_file

STRIPE_API = 'https://api.stripe.com/v1'
WEBHOOK_TOLERANCE_S = 300
KEY_FILES = {'test': 'stripe-test.key', 'live': 'stripe-live.key'}
WEBHOOK_FILES = {
    'test': 'stripe-webhook-test.key',
    'live': 'stripe-webhook-live.key',
}


class RailError(ValueError):
    pass


def stripe_keys(
    mode: str = 'test', root: Path | None = None
) -> tuple[str, str]:
    """Clés Stripe depuis le sidecar (jamais loguées, jamais en dur).

    Args:
        mode: test | live (fichiers distincts).
        root: config_root (défaut : instance).

    Returns:
        Tuple (api_key, webhook_secret), '' si absents.
    """
    if mode not in KEY_FILES:
        raise RailError('MODE: test|live')
    base = (root or config_root()) / 'secrets'
    return (
        read_secret_file(base / KEY_FILES[mode]),
        read_secret_file(base / WEBHOOK_FILES[mode]),
    )


def _cents(amount_eur: float) -> int:
    if amount_eur <= 0:
        raise RailError('API: montant <= 0')
    return int(round(float(amount_eur) * 100))


class StripeRail:
    """Client Stripe minimal (test-first, fail-closed)."""

    def __init__(
        self,
        api_key: str,
        webhook_secret: str = '',
        mode: str = 'test',
        timeout: float = 20.0,
    ):
        if mode not in {'test', 'live'}:
            raise RailError('MODE: test|live')
        prefixes = {
            'test': ('sk_test_', 'rk_test_'),
            'live': ('sk_live_', 'rk_live_'),
        }
        if not api_key.startswith(prefixes[mode]):
            raise RailError(f'MODE: clé {mode} requise (sk_|rk_)')
        self.api_key = api_key
        self.webhook_secret = webhook_secret
        self.mode = mode
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        idempotency_key: str = '',
    ) -> dict[str, Any]:
        auth = base64.b64encode(f'{self.api_key}:'.encode()).decode()
        headers = {'Authorization': f'Basic {auth}'}
        if idempotency_key:
            headers['Idempotency-Key'] = idempotency_key
        data = None
        if params is not None:
            body = urllib.parse.urlencode(
                {key: str(value) for key, value in params.items()}
            )
            data = body.encode('utf-8')
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
        request = urllib.request.Request(
            f'{STRIPE_API}{path}', data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout
            ) as response:
                payload = json.loads(response.read().decode('utf-8'))
        except urllib.error.HTTPError as exc:
            raise self._api_error(exc) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RailError(f'NETWORK: {exc}') from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RailError(f'API: réponse illisible ({exc})') from exc
        if not isinstance(payload, dict):
            raise RailError('API: réponse non-objet')
        return payload

    @staticmethod
    def _api_error(exc: urllib.error.HTTPError) -> RailError:
        if exc.code == 401:
            return RailError('AUTH: clé Stripe rejetée')
        try:
            payload = json.loads(exc.read().decode('utf-8'))
        except (OSError, ValueError, UnicodeDecodeError):
            return RailError(f'API: HTTP {exc.code}')
        detail = (
            (payload.get('error') or {}) if isinstance(payload, dict) else {}
        )
        code = detail.get('code', f'HTTP {exc.code}')
        message = str(detail.get('message', ''))[:200]
        return RailError(f'API: {code} {message}'.strip())

    def create_payment_intent(
        self,
        amount_eur: float,
        currency: str = 'eur',
        payment_method: str = 'pm_card_visa',
        confirm: bool = True,
        description: str = '',
        idempotency_key: str = '',
    ) -> dict[str, Any]:
        """Crée (+ confirme) un PaymentIntent. Retourne l'objet Stripe.

        Raises:
            RailError: AUTH, NETWORK, API, MODE.
        """
        return self._request(
            'POST',
            '/payment_intents',
            {
                'amount': _cents(amount_eur),
                'currency': currency.lower(),
                'payment_method': payment_method,
                'confirm': 'true' if confirm else 'false',
                'description': description[:200],
            },
            idempotency_key,
        )

    def get_payment_intent(self, pi_id: str) -> dict[str, Any]:
        """Relit un PaymentIntent (rapprochement)."""
        if not pi_id.startswith('pi_'):
            raise RailError('API: pi_id invalide')
        return self._request(
            'GET', f'/payment_intents/{urllib.parse.quote(pi_id)}'
        )

    def refund(
        self,
        payment_intent_id: str,
        amount_eur: float | None = None,
        idempotency_key: str = '',
    ) -> dict[str, Any]:
        """Rembourse (total si montant omis). Retourne l'objet Stripe."""
        if not payment_intent_id.startswith('pi_'):
            raise RailError('API: pi_id invalide')
        params: dict[str, Any] = {'payment_intent': payment_intent_id}
        if amount_eur is not None:
            params['amount'] = _cents(amount_eur)
        return self._request('POST', '/refunds', params, idempotency_key)

    def parse_webhook(
        self, raw_body: bytes, sig_header: str, now: float | None = None
    ) -> dict[str, Any]:
        """Vérifie (HMAC + fraîcheur) puis parse un webhook Stripe.

        Args:
            raw_body: Corps brut exact.
            sig_header: En-tête Stripe-Signature (t=...,v1=...).
            now: Timestamp (défaut : time.time, injectable en test).

        Returns:
            L'événement Stripe vérifié.

        Raises:
            RailError: SIGNATURE, STALE, API (JSON).
        """
        if not self.webhook_secret:
            raise RailError('SIGNATURE: secret webhook manquant')
        parts = dict(
            item.split('=', 1) for item in sig_header.split(',') if '=' in item
        )
        timestamp = parts.get('t', '')
        signatures = [
            value
            for key, value in (
                item.split('=', 1)
                for item in sig_header.split(',')
                if '=' in item
            )
            if key.strip() == 'v1'
        ]
        if not timestamp or not signatures:
            raise RailError('SIGNATURE: en-tête incomplet')
        try:
            age = abs(
                (now if now is not None else time.time()) - int(timestamp)
            )
        except ValueError as exc:
            raise RailError('SIGNATURE: timestamp invalide') from exc
        if age > WEBHOOK_TOLERANCE_S:
            raise RailError('STALE: webhook trop ancien')
        signed = f'{timestamp}.'.encode() + raw_body
        expected = hmac.new(
            self.webhook_secret.encode(), signed, hashlib.sha256
        ).hexdigest()
        if not any(hmac.compare_digest(expected, sig) for sig in signatures):
            raise RailError('SIGNATURE: HMAC invalide')
        try:
            payload = json.loads(raw_body.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise RailError('API: webhook illisible') from exc
        if not isinstance(payload, dict):
            raise RailError('API: webhook non-objet')
        return payload
