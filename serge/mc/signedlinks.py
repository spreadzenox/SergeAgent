#!/usr/bin/env python3
"""Liens signés HMAC expirables (E7, §8.1) pour écrans sensibles / audio."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def signer_url(
    url_base: str,
    secret: str,
    ttl_s: int = 3600,
    now_fn: Callable[[], float] | None = None,
) -> str:
    """Génère une URL signée HMAC-SHA256 avec expiration.

    Args:
        url_base: URL de base (chemin ou URL complète).
        secret: Secret serveur (ex: owner_token).
        ttl_s: Durée de validité en secondes.
        now_fn: Horloge epoch (défaut : time.time).

    Returns:
        URL avec paramètres `exp` et `sig`.
    """
    now = now_fn() if callable(now_fn) else time.time()
    expires = int(now + ttl_s)

    parts = urlsplit(url_base)
    query_dict = dict(parse_qsl(parts.query))
    query_dict['exp'] = str(expires)

    # Base à signer : path + '?' + query sans sig
    query_str = urlencode(sorted(query_dict.items()))
    base_a_signer = f'{parts.path}?{query_str}'

    sig = hmac.new(
        secret.encode('utf-8'),
        base_a_signer.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64.urlsafe_b64encode(sig).decode('ascii').rstrip('=')

    query_dict['sig'] = sig_b64
    new_query = urlencode(sorted(query_dict.items()))
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, new_query, parts.fragment)
    )


def verifier_url(
    url_ou_chemin: str,
    secret: str,
    now_fn: Callable[[], float] | None = None,
) -> bool:
    """Vérifie la signature et l'expiration d'une URL signée.

    Args:
        url_ou_chemin: URL ou chemin avec query `exp` et `sig`.
        secret: Secret serveur attendu.
        now_fn: Horloge epoch (défaut : time.time).

    Returns:
        True si signature valide et non expirée, False sinon.
    """
    parts = urlsplit(url_ou_chemin)
    query_dict = dict(parse_qsl(parts.query))

    sig_recue = query_dict.pop('sig', None)
    exp_str = query_dict.get('exp')
    if not sig_recue or not exp_str:
        return False

    try:
        expires = int(exp_str)
    except ValueError:
        return False

    now = now_fn() if callable(now_fn) else time.time()
    if now > expires:
        return False

    query_str = urlencode(sorted(query_dict.items()))
    base_a_signer = f'{parts.path}?{query_str}'

    sig_attendue = hmac.new(
        secret.encode('utf-8'),
        base_a_signer.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    sig_attendue_b64 = (
        base64.urlsafe_b64encode(sig_attendue).decode('ascii').rstrip('=')
    )

    return hmac.compare_digest(sig_recue, sig_attendue_b64)
