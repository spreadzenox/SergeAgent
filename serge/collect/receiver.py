#!/usr/bin/env python3
"""Écouteur Stripe : POST /hooks/stripe → ledger paid (HMAC vérifié)."""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from serge.collect.rails import RailError, stripe_keys  # noqa: E402
from serge.collect.webhook import (  # noqa: E402
    STRIPE_WEBHOOK_PATH,
    apply_event,
    verify_event,
)
from serge.db.store import default_canon_path, open_db  # noqa: E402

DEFAULT_LISTEN = '127.0.0.1:8788'
MAX_BODY = 262144


class StripeReceiverError(ValueError):
    pass


def load_secrets() -> dict[str, str]:
    """Charge les `whsec` test/live depuis les fichiers 0600 d’instance.

    Returns:
        Dict `live` / `test` → secret, au moins une entrée.

    Raises:
        StripeReceiverError: Aucun `whsec` lisible.
    """
    secrets: dict[str, str] = {}
    for mode in ('live', 'test'):
        _key, whsec = stripe_keys(mode)
        if whsec.strip():
            secrets[mode] = whsec.strip()
    if not secrets:
        raise StripeReceiverError('aucun whsec Stripe (test ou live)')
    return secrets


class Handler(BaseHTTPRequestHandler):
    secrets: dict[str, str] = {}
    db_path: Path = Path()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: N802, A002
        sys.stderr.write('stripe-receiver: %s\n' % (format % args))

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path.split('?', 1)[0] == '/healthz':
            self._send(200, {'status': 'ok', 'stripe': True})
            return
        self._send(404, {'error': 'not_found'})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split('?', 1)[0]
        if path != STRIPE_WEBHOOK_PATH:
            self._send(404, {'error': 'not_found'})
            return
        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {'error': 'bad_length'})
            return
        raw = self.rfile.read(length)
        sig = self.headers.get('Stripe-Signature') or ''
        try:
            mode, event = verify_event(raw, sig, self.secrets)
        except RailError as exc:
            message = str(exc)
            code = 400 if message.startswith('STALE') else 401
            self._send(code, {'error': 'unauthorized'})
            return
        conn = open_db(self.db_path)
        try:
            result = apply_event(conn, event)
            conn.commit()
        finally:
            conn.close()
        result['mode'] = mode
        self._send(200, result)


def serve(listen: str = DEFAULT_LISTEN) -> int:
    """Écoute loopback jusqu’à interruption.

    Args:
        listen: `hôte:port` (défaut `127.0.0.1:8788`).

    Returns:
        0 si arrêt propre, 2 si secrets ou canon illisibles.
    """
    try:
        secrets = load_secrets()
        db_path = default_canon_path()
        open_db(db_path).close()
    except (StripeReceiverError, OSError) as exc:
        sys.stderr.write(f'stripe-receiver: refusé: {exc}\n')
        return 2
    host, _, port_raw = listen.rpartition(':')
    Handler.secrets = secrets
    Handler.db_path = db_path
    server = ThreadingHTTPServer(
        (host or '127.0.0.1', int(port_raw or '8788')), Handler
    )
    sys.stderr.write(f'stripe-receiver: écoute {listen}\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if args and args[0] == 'serve':
        listen = DEFAULT_LISTEN
        if '--listen' in args:
            listen = args[args.index('--listen') + 1]
        else:
            listen = os.environ.get(
                'SERGE_STRIPE_RECEIVER_LISTEN', DEFAULT_LISTEN
            )
        return serve(listen)
    sys.stderr.write('usage: receiver.py serve [--listen 127.0.0.1:8788]\n')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
