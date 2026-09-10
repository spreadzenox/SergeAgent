#!/usr/bin/env python3
"""MC HTTP : ThreadingHTTPServer, routage, statiques, headers sécu."""

from __future__ import annotations

import hmac
import json
import sys
import urllib.parse
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from sqlite3 import Connection

from serge.db.store import open_db
from serge.mc.auth import (
    COOKIE_NAME,
    SESSION_TTL_S,
    RateLimiter,
    check_owner,
    create_session,
    revoke_session,
)
from serge.mc.proj_trace import project_trace
from serge.mc.projectors import PAGE_SECTIONS, SnapshotCache
from serge.mc.sse import state_payload, stream_page
from serge.policy import PolicyError, load_policy

STATIC_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript',
    '.css': 'text/css',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
}
SECURITY_HEADERS = {
    'Content-Security-Policy': (
        "default-src 'self'; base-uri 'self';"
        " frame-ancestors 'none'; form-action 'self'"
    ),
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
}
REQUIRED_TEMPLATES = ('login.html', 'shell.html', 'error.html')
MAX_FORM_BYTES = 4096


@dataclass(frozen=True)
class McConfig:
    """Config serveur MC (immuable, construite au boot)."""

    db_path: Path
    owner_token: str
    static_dir: Path
    templates_dir: Path
    limiter: RateLimiter
    policy_dir: Path | None = None


class McHandler(BaseHTTPRequestHandler):
    """Routes MC (config via create_server, jamais de global mutable)."""

    app_config: McConfig
    server_version = 'SergeMC/1'
    sys_version = ''
    protocol_version = 'HTTP/1.1'

    def log_message(self, format: str, *args: object) -> None:
        print(f'mc {self.command} {self.path.split("?")[0]}', file=sys.stderr)

    def end_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    @contextmanager
    def _db(self) -> Iterator[Connection]:
        conn = open_db(self.app_config.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, code: int, html: str) -> None:
        self._send(code, html.encode('utf-8'), 'text/html; charset=utf-8')

    def _template(self, name: str) -> str:
        return (self.app_config.templates_dir / name).read_text(
            encoding='utf-8'
        )

    def _send_json(self, code: int, obj: dict) -> None:
        self._send(
            code,
            json.dumps(obj, ensure_ascii=False).encode('utf-8'),
            'application/json',
        )

    def _query(self) -> dict[str, str]:
        parsed = urllib.parse.parse_qs(
            urllib.parse.urlsplit(self.path).query, keep_blank_values=True
        )
        return {key: values[0] for key, values in parsed.items() if values}

    def _policy(self) -> dict | None:
        try:
            return load_policy(self.app_config.policy_dir)
        except PolicyError:
            return None

    def _cookies(self) -> dict[str, str]:
        jar = SimpleCookie()
        jar.load(self.headers.get('Cookie') or '')
        return {key: morsel.value for key, morsel in jar.items()}

    def _headers_lower(self) -> dict[str, str]:
        return {key.lower(): value for key, value in self.headers.items()}

    def _is_owner(self) -> bool:
        with self._db() as conn:
            return check_owner(
                self._headers_lower(),
                self._cookies(),
                conn,
                self.app_config.owner_token,
            )

    def _serve_static(self, rel: str) -> None:
        base = self.app_config.static_dir.resolve()
        target = (base / rel).resolve()
        if base not in target.parents and target != base:
            self._error(404)
            return
        content_type = STATIC_TYPES.get(target.suffix.lower(), '')
        if not content_type or not target.is_file():
            self._error(404)
            return
        self._send(200, target.read_bytes(), content_type)

    def _error(self, code: int) -> None:
        messages = {
            400: 'Requête illisible.',
            404: 'Page introuvable.',
            413: 'Requête trop volumineuse.',
            429: 'Trop d’essais — attends une minute.',
            500: 'Service momentanément indisponible.',
        }
        html = self._template('error.html')
        html = html.replace('{code}', str(code))
        html = html.replace('{message}', messages.get(code, 'Erreur.'))
        self._send_html(code, html)

    def do_GET(self) -> None:  # noqa: N802 (nom imposé http.server)
        """Route GET (pages, santé, statiques)."""
        path = urllib.parse.unquote(
            urllib.parse.urlsplit(self.path).path or '/'
        )
        if path == '/healthz':
            self._send_json(200, {'status': 'ok'})
            return
        if path == '/robots.txt':
            self._send(
                200, b'User-agent: *\nDisallow: /owner/\n', 'text/plain'
            )
            return
        if path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
            return
        if path == '/owner/login':
            self._send_html(200, self._template('login.html'))
            return
        if path == '/owner':
            if not self._is_owner():
                self.send_response(302)
                self.send_header('Location', '/owner/login')
                self.end_headers()
                return
            policy = self._policy()
            if policy is None:
                self._error(500)
                return
            payload = state_payload(
                self.app_config.db_path, policy, 'p0', PAGE_SECTIONS['p0']
            )
            blob = json.dumps(payload, ensure_ascii=False).replace(
                '<', '\\u003c'
            )
            html = self._template('shell.html').replace('<!--BOOT-->', blob)
            self._send_html(200, html)
            return
        if path == '/owner/api/state':
            self._api_state()
            return
        if path == '/owner/api/stream':
            self._api_stream()
            return
        if path == '/owner/api/trace':
            self._api_trace()
            return
        if path == '/static/' or path.startswith('/static/'):
            self._serve_static(path[len('/static/') :])
            return
        self._error(404)

    def _require_owner(self) -> bool:
        if self._is_owner():
            return True
        self._send_json(
            401,
            {
                'erreur': 'Authentification requise.',
                'code': 'auth',
                'aide': 'Reconnecte-toi via /owner/login.',
            },
        )
        return False

    def _api_common(self) -> tuple[str, list[str], dict] | None:
        if not self._require_owner():
            return None
        page = self._query().get('page', '')
        sections = PAGE_SECTIONS.get(page)
        if sections is None:
            self._send_json(
                400,
                {
                    'erreur': f'Page inconnue : {page}.',
                    'code': 'page',
                    'aide': 'Pages : p0.',
                },
            )
            return None
        policy = self._policy()
        if policy is None:
            self._send_json(
                500,
                {
                    'erreur': 'Policy illisible.',
                    'code': 'policy',
                    'aide': 'Vérifie config/policy.yaml.',
                },
            )
            return None
        return page, sections, policy

    def _api_state(self) -> None:
        ready = self._api_common()
        if ready is None:
            return
        page, sections, policy = ready
        payload = state_payload(
            self.app_config.db_path, policy, page, sections
        )
        self._send_json(200, payload)

    def _api_stream(self) -> None:
        ready = self._api_common()
        if ready is None:
            return
        page, sections, policy = ready
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.end_headers()
        try:
            stream_page(
                self.wfile,
                self.app_config.db_path,
                policy,
                page,
                sections,
                SnapshotCache(),
            )
        except (BrokenPipeError, ConnectionResetError):
            return

    def _api_trace(self) -> None:
        if not self._require_owner():
            return
        item_id = self._query().get('item', '')
        if not item_id:
            self._send_json(
                400,
                {
                    'erreur': 'Paramètre item requis.',
                    'code': 'item',
                    'aide': 'Exemple : …/api/trace?item=w1.',
                },
            )
            return
        with self._db() as conn:
            trace = project_trace(conn, item_id)
        if trace is None:
            self._send_json(
                404,
                {
                    'erreur': 'Tâche introuvable.',
                    'code': 'trace',
                    'aide': 'Vérifie l’identifiant.',
                },
            )
            return
        self._send_json(200, trace)

    def do_POST(self) -> None:  # noqa: N802 (nom imposé http.server)
        """Route POST (login, logout)."""
        path = urllib.parse.unquote(
            urllib.parse.urlsplit(self.path).path or '/'
        )
        if path == '/owner/login':
            self._login()
            return
        if path == '/owner/logout':
            self._logout()
            return
        self._error(404)

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

    def _login(self) -> None:
        ip = self.client_address[0]
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
            or not hmac.compare_digest(token, expected)
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
        self.send_header(
            'Set-Cookie',
            f'{COOKIE_NAME}={session}; HttpOnly; Path=/owner;'
            f' SameSite=Lax; Max-Age={SESSION_TTL_S}',
        )
        self.end_headers()

    def _logout(self) -> None:
        token = self._cookies().get(COOKIE_NAME, '')
        with self._db() as conn:
            revoke_session(conn, token)
        self.send_response(302)
        self.send_header('Location', '/owner/login')
        self.send_header(
            'Set-Cookie',
            f'{COOKIE_NAME}=; HttpOnly; Path=/owner; SameSite=Lax; Max-Age=0',
        )
        self.end_headers()


def create_server(
    config: McConfig, host: str = '127.0.0.1', port: int = 0
) -> ThreadingHTTPServer:
    """Crée le serveur MC (bind loopback, port auto en test).

    Args:
        config: Config immuable (DB, token, assets, limiter).
        host: Interface d'écoute (jamais 0.0.0.0 ici).
        port: Port (0 = auto, tests).

    Returns:
        Serveur threadé prêt (appelant : serve_forever).

    Raises:
        ValueError: Si un template requis manque (fail-fast au boot).
    """
    for name in REQUIRED_TEMPLATES:
        if not (config.templates_dir / name).is_file():
            raise ValueError(f'template MC manquant : {name}')
    McHandler.app_config = config
    server = ThreadingHTTPServer((host, port), McHandler)
    server.daemon_threads = True
    return server
