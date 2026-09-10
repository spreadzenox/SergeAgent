#!/usr/bin/env python3
"""MC auth : token owner, sessions cookie 12 h, rate-limit login."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from serge.db.store import utcnow

SESSION_TTL_S = 12 * 3600
LOGIN_RATE_MAX = 10
LOGIN_RATE_WINDOW_S = 60
COOKIE_NAME = 'serge_mc'


def hash_token(token: str) -> str:
    """Empreinte SHA256 d'un token (jamais stocké en clair).

    Args:
        token: Token brut (session).

    Returns:
        Hex du SHA256 (clé de `mc_sessions`).
    """
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def _expires_at(now_iso: str, ttl_s: int = SESSION_TTL_S) -> str:
    moment = datetime.fromisoformat(now_iso)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (moment + timedelta(seconds=ttl_s)).isoformat()


def create_session(
    conn: sqlite3.Connection, now_iso: str | None = None
) -> tuple[str, str]:
    """Crée une session (commit par l'appelant).

    Args:
        conn: Connexion canon.
        now_iso: Maintenant ISO UTC (défaut : horloge canon).

    Returns:
        Tuple (token brut pour le cookie, expires_at ISO).
    """
    token = secrets.token_urlsafe(32)
    now = now_iso or utcnow()
    expires = _expires_at(now)
    conn.execute(
        'INSERT INTO mc_sessions(token_hash, created_at, expires_at)'
        ' VALUES(?,?,?)',
        (hash_token(token), now, expires),
    )
    return token, expires


def verify_session(
    conn: sqlite3.Connection, token: str, now_iso: str | None = None
) -> bool:
    """Session valide et non expirée (+ touche last_seen, commit appelant).

    Args:
        conn: Connexion canon (lecture + touche).
        token: Token brut du cookie.
        now_iso: Maintenant ISO UTC (défaut : horloge canon).

    Returns:
        True si la session existe et n'a pas expiré.
    """
    if not token:
        return False
    now = now_iso or utcnow()
    row = conn.execute(
        'SELECT expires_at FROM mc_sessions WHERE token_hash=?',
        (hash_token(token),),
    ).fetchone()
    if row is None or str(row[0]) <= now:
        return False
    conn.execute(
        'UPDATE mc_sessions SET last_seen_at=? WHERE token_hash=?',
        (now, hash_token(token)),
    )
    return True


def revoke_session(conn: sqlite3.Connection, token: str) -> None:
    """Révoque une session (commit par l'appelant).

    Args:
        conn: Connexion canon.
        token: Token brut du cookie (vide = sans effet).
    """
    if token:
        conn.execute(
            'DELETE FROM mc_sessions WHERE token_hash=?',
            (hash_token(token),),
        )


def check_owner(
    headers: Mapping[str, str],
    cookies: Mapping[str, str],
    conn: sqlite3.Connection,
    expected_token: str,
    now_iso: str | None = None,
) -> bool:
    """Bearer/header/cookie valides ? (compare_digest, jamais logué).

    Args:
        headers: En-têtes HTTP (clés en minuscules).
        cookies: Cookies parsés.
        conn: Connexion canon (sessions).
        expected_token: Token owner du sidecar.
        now_iso: Maintenant ISO UTC (défaut : horloge canon).

    Returns:
        True si bearer, header dédié ou session valides.
    """
    auth = str(headers.get('authorization') or '')
    if auth.lower().startswith('bearer '):
        candidate = auth[7:].strip()
        if candidate and expected_token:
            if hmac.compare_digest(candidate, expected_token):
                return True
    header_token = str(headers.get('x-serge-owner-token') or '').strip()
    if header_token and expected_token:
        if hmac.compare_digest(header_token, expected_token):
            return True
    cookie_token = str(cookies.get(COOKIE_NAME) or '').strip()
    return bool(cookie_token) and verify_session(conn, cookie_token, now_iso)


class RateLimiter:
    """Fenêtre glissante en mémoire (10 coups/min/clé par défaut)."""

    def __init__(
        self,
        max_hits: int = LOGIN_RATE_MAX,
        window_s: float = LOGIN_RATE_WINDOW_S,
        now_fn: Callable[[], float] | None = None,
    ) -> None:
        """Construit un limiteur (état interne, jamais persisté).

        Args:
            max_hits: Coups autorisés par fenêtre.
            window_s: Fenêtre glissante en secondes.
            now_fn: Horloge (défaut : monotonic, injectable en test).
        """
        self.max_hits = max_hits
        self.window_s = window_s
        self._now = now_fn or time.monotonic
        self._hits: dict[str, list[float]] = {}

    def allow(self, key: str) -> bool:
        """True + consomme si sous le plafond, sinon False (sans consommer).

        Args:
            key: Clé de comptage (ex. IP source).

        Returns:
            True si le coup est autorisé.
        """
        now = self._now()
        recent = [
            tick
            for tick in self._hits.get(key, [])
            if now - tick < self.window_s
        ]
        if len(recent) >= self.max_hits:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True
