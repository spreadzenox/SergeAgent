#!/usr/bin/env python3
"""Loopback SMS webhook receiver: Android gateway -> SmsInbox.

The Android phone pushes inbound SMS here (via Caddy sms.<domain> route).
This process authenticates, rate-limits, normalizes the provider payload
into the broker envelope, and ingests. It stores nothing itself: SmsInbox
keeps OTP hashes only, never raw bodies.

Auth (any one, in preference order):
  1. X-SMS-Signature: HMAC-SHA256(secret, raw_body) hex
  2. X-SMS-Token: shared secret itself (for apps without signing)
  3. ?token=<secret> query param (last resort, HTTPS only via ingress)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import tomllib
import urllib.parse
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from serge.sms.inbox import SmsBrokerDenied, SmsInbox  # noqa: E402

DEFAULT_LISTEN = '127.0.0.1:8787'
MAX_BODY = 65536
GLOBAL_PER_MINUTE = 60
SENDER_PER_MINUTE = 10


class SmsReceiverError(ValueError):
    pass


def _as_iso(value: Any) -> str:
    if isinstance(value, (int, float)):
        stamp = float(value)
        if stamp > 1e12:  # epoch milliseconds
            stamp /= 1000.0
        return datetime.fromtimestamp(stamp, UTC).isoformat()
    text = str(value or '').strip()
    if not text:
        return datetime.now(UTC).isoformat()
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return datetime.now(UTC).isoformat()
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def normalize_envelope(payload: Any) -> dict[str, str]:
    """Accept the canonical envelope or common Android-gateway shapes."""
    if not isinstance(payload, dict):
        raise SmsReceiverError('payload must be a JSON object')
    if set(payload) == {'id', 'from', 'body', 'received_at'}:
        return {
            key: str(payload[key])
            for key in ('id', 'from', 'body', 'received_at')
        }
    inner = (
        payload.get('payload')
        if isinstance(payload.get('payload'), dict)
        else payload
    )
    get = inner.get if isinstance(inner, dict) else payload.get
    message_id = get('id') or get('messageId') or get('uuid') or get('smsId')
    sender = (
        get('phoneNumber')
        or get('from')
        or get('sender')
        or get('address')
        or get('originator')
    )
    body = get('message') or get('body') or get('text') or get('content')
    received = (
        get('receivedAt')
        or get('received_at')
        or get('timestamp')
        or get('date')
        or get('createdAt')
    )
    if not message_id or not sender or not body:
        raise SmsReceiverError('unmappable SMS payload shape')
    return {
        'id': str(message_id),
        'from': str(sender),
        'body': str(body),
        'received_at': _as_iso(received),
    }


def check_auth(
    raw_body: bytes,
    headers: Any,
    query: dict[str, list[str]],
    secret: bytes,
) -> str:
    """Return the auth method used, or raise."""
    if len(secret) < 16:
        raise SmsReceiverError('webhook secret too short')
    signature = (headers.get('X-SMS-Signature') or '').strip()
    if signature:
        expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
        if hmac.compare_digest(expected, signature):
            return 'hmac'
        raise SmsReceiverError('bad signature')
    token = (headers.get('X-SMS-Token') or '').strip()
    if not token:
        values = query.get('token') or []
        token = str(values[0]).strip() if values else ''
    if token and hmac.compare_digest(token, secret.decode('utf-8', 'replace')):
        return 'token'
    raise SmsReceiverError('missing or invalid auth')


class RateLimiter:
    def __init__(
        self,
        *,
        global_per_minute: int = GLOBAL_PER_MINUTE,
        sender_per_minute: int = SENDER_PER_MINUTE,
    ):
        self.global_per_minute = global_per_minute
        self.sender_per_minute = sender_per_minute
        self._global: list[float] = []
        self._senders: dict[str, list[float]] = {}

    def _prune(self, stamps: list[float], now: float) -> list[float]:
        cutoff = now - 60.0
        kept = [stamp for stamp in stamps if stamp >= cutoff]
        del stamps[:]
        stamps.extend(kept)
        return stamps

    def allow(self, sender_hash: str, now: float | None = None) -> bool:
        moment = time.time() if now is None else now
        self._prune(self._global, moment)
        if len(self._global) >= self.global_per_minute:
            return False
        bucket = self._prune(self._senders.setdefault(sender_hash, []), moment)
        if len(bucket) >= self.sender_per_minute:
            return False
        self._global.append(moment)
        bucket.append(moment)
        return True


def resolve_secret() -> bytes:
    override = os.environ.get('SERGE_SMS_GATEWAY_TOKEN_FILE', '').strip()
    if override:
        path = Path(override)
    else:
        instance_file = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
        if not instance_file:
            raise SmsReceiverError('SERGE_INSTANCE_FILE is required')
        try:
            data = tomllib.loads(
                Path(instance_file).read_text(encoding='utf-8')
            )
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise SmsReceiverError('instance file unreadable') from exc
        paths = data.get('paths') or {}
        home = Path(str(paths.get('home') or os.path.expanduser('~')))
        config_root = Path(
            str(paths.get('config_root') or '') or str(home / '.config/serge')
        )
        path = config_root / 'secrets/sms-gateway.token'
    try:
        return path.read_bytes().strip()
    except OSError as exc:
        raise SmsReceiverError(f'webhook secret unreadable: {path}') from exc


def resolve_db() -> Path:
    root = Path(
        os.environ.get('SERGE_SYSTEM_ROOT', '/home/serge/serge-system')
    )
    return root / 'state/sms/inbound.db'


def ingest_payload(
    raw_body: bytes,
    headers: Any,
    query: dict[str, list[str]],
    *,
    secret: bytes,
    inbox: SmsInbox,
    limiter: RateLimiter,
) -> dict[str, Any]:
    method = check_auth(raw_body, headers, query, secret)
    try:
        payload = json.loads(raw_body.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmsReceiverError('invalid JSON') from exc
    envelope = normalize_envelope(payload)
    sender_hash = hashlib.sha256(envelope['from'].encode('utf-8')).hexdigest()
    if not limiter.allow(sender_hash):
        raise SmsReceiverError('rate_limited')
    canonical = json.dumps(envelope, sort_keys=True).encode('utf-8')
    signature = hmac.new(secret, canonical, hashlib.sha256).hexdigest()
    try:
        result = inbox.ingest(
            canonical, signature, secret, purpose='ACCOUNT_VERIFICATION'
        )
    except SmsBrokerDenied as exc:
        raise SmsReceiverError(str(exc)) from exc
    return {
        'status': result['status'],
        'provider_message_id': result['provider_message_id'],
        'otp_present': result.get('otp') is not None,
        'auth': method,
    }


class Handler(BaseHTTPRequestHandler):
    secret: bytes = b''
    inbox: SmsInbox | None = None
    limiter: RateLimiter = RateLimiter()

    # Param name `format` matches BaseHTTPRequestHandler (Liskov).
    def log_message(self, format: str, *args: Any) -> None:  # noqa: N802, A002
        sys.stderr.write('sms-receiver: %s\n' % (format % args))

    def _send(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == '/healthz':
            db_ok = bool(self.inbox and self.inbox.db_path.is_file())
            self._send(200, {'status': 'ok', 'sms_db': db_ok})
            return
        self._send(404, {'error': 'not_found'})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/hooks/sms':
            self._send(404, {'error': 'not_found'})
            return
        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY:
            self._send(400, {'error': 'bad_length'})
            return
        raw_body = self.rfile.read(length)
        assert self.inbox is not None
        try:
            result = ingest_payload(
                raw_body,
                self.headers,
                urllib.parse.parse_qs(parsed.query),
                secret=self.secret,
                inbox=self.inbox,
                limiter=self.limiter,
            )
        except SmsReceiverError as exc:
            message = str(exc)
            if message == 'rate_limited':
                self._send(429, {'error': message})
            elif message in {'bad signature', 'missing or invalid auth'}:
                self._send(401, {'error': 'unauthorized'})
            else:
                self._send(400, {'error': message})
            return
        self._send(200, result)


def serve(listen: str = DEFAULT_LISTEN) -> int:
    try:
        secret = resolve_secret()
        db_path = resolve_db()
        inbox = SmsInbox(db_path)
        try:
            db_path.chmod(0o600)
        except OSError:
            pass
    except (SmsReceiverError, OSError) as exc:
        sys.stderr.write(f'sms-receiver: refusé: {exc}\n')
        return 2
    host, _, port_raw = listen.rpartition(':')
    Handler.secret = secret
    Handler.inbox = inbox
    Handler.limiter = RateLimiter()
    server = ThreadingHTTPServer(
        (host or '127.0.0.1', int(port_raw or '8787')), Handler
    )
    sys.stderr.write(f'sms-receiver: écoute {listen}\n')
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
                'SERGE_SMS_RECEIVER_LISTEN', DEFAULT_LISTEN
            )
        return serve(listen)
    sys.stderr.write('usage: receiver.py serve [--listen 127.0.0.1:8787]\n')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
