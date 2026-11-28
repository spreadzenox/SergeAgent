#!/usr/bin/env python3
"""La connexion et la déconnexion du propriétaire (formulaire, cookie)."""

from __future__ import annotations

import hmac
import urllib.parse
from contextlib import AbstractContextManager
from sqlite3 import Connection
from typing import TYPE_CHECKING, Any, Protocol

from serge.mc.actions import MAX_FORM_BYTES
from serge.mc.auth import (
    COOKIE_NAME,
    SESSION_TTL_S,
    client_ip,
    create_session,
    revoke_session,
)


class _Handler(Protocol):
    headers: Any
    rfile: Any
    app_config: Any
    client_address: Any

    def _db(self) -> AbstractContextManager[Connection]: ...
    def _cookies(self) -> dict[str, str]: ...
    def _headers_lower(self) -> dict[str, str]: ...
    def _template(self, name: str) -> str: ...
    def _send_html(self, code: int, html: str) -> None: ...
    def _error(self, code: int) -> None: ...
    def send_response(self, code: int, message: str | None = None) -> None: ...
    def send_header(self, keyword: str, value: str) -> None: ...
    def end_headers(self) -> None: ...


if TYPE_CHECKING:
    _Base = _Handler
else:
    _Base = object


class SessionMixin(_Base):
    """POST /owner/login et /owner/logout."""

    def _form(self) -> dict[str, str] | None:
        try:
            length = int(self.headers.get('Content-Length') or 0)
        except (TypeError, ValueError):
            return None
        if length < 0 or length > MAX_FORM_BYTES:
            return None
        raw = self.rfile.read(length) if length else b''
        parsed = urllib.parse.parse_qs(
            raw.decode('utf-8', 'replace'), keep_blank_values=True
        )
        return {key: values[0] for key, values in parsed.items() if values}

    def _cookie(self, valeur: str, duree: int) -> str:
        # ``Secure`` dès que le visiteur est venu en HTTPS (Caddy le dit) :
        # le cookie ne repart jamais en clair. Pas sur un poste de
        # développement, servi en HTTP sur 127.0.0.1.
        https = self.headers.get('X-Forwarded-Proto') == 'https'
        return (
            f'{COOKIE_NAME}={valeur}; HttpOnly; Path=/owner; SameSite=Lax;'
            f' Max-Age={duree}' + ('; Secure' if https else '')
        )

    def _login(self) -> None:
        ip = client_ip(self.client_address[0], self._headers_lower())
        if not self.app_config.limiter.allow(ip):
            html = self._template('login.html').replace(
                'data-error="rate" hidden', 'data-error="rate"'
            )
            self._send_html(429, html)
            return
        form = self._form()
        if form is None:
            self._error(413)
            return
        token = form.get('token') or ''
        expected = self.app_config.owner_token
        if (
            not token
            or not expected
            or not hmac.compare_digest(token.encode(), expected.encode())
        ):
            html = self._template('login.html').replace(
                'data-error="auth" hidden', 'data-error="auth"'
            )
            self._send_html(401, html)
            return
        with self._db() as conn:
            session, _ = create_session(conn)
        self.send_response(302)
        self.send_header('Location', '/owner')
        self.send_header('Content-Length', '0')
        self.send_header('Set-Cookie', self._cookie(session, SESSION_TTL_S))
        self.end_headers()

    def _logout(self) -> None:
        token = self._cookies().get(COOKIE_NAME, '')
        with self._db() as conn:
            revoke_session(conn, token)
        self.send_response(302)
        self.send_header('Location', '/owner/login')
        self.send_header('Content-Length', '0')
        self.send_header('Set-Cookie', self._cookie('', 0))
        self.end_headers()
