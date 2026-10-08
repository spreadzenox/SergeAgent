#!/usr/bin/env python3
"""Voice bridge daemon: broker-gated originate + trunk health + consent CLI.

Loopback HTTP (127.0.0.1:8791). Never exposed directly; Caddy does not
route here. originate() goes through voice policy first, then
Asterisk `channel originate` with the locked NPV CLI. No broker allow,
no dial.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
import urllib.parse
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from serge.db.store import default_canon_path  # noqa: E402
from serge.e164 import E164_RE  # noqa: E402
from serge.funnels.contacts import normalise_value  # noqa: E402
from serge.paths import config_root, system_root  # noqa: E402
from serge.voice.ledger import VoiceLedger  # noqa: E402
from serge.voice.policy import (  # noqa: E402
    VoiceBrokerDenied,
    call_limits,
    default_ledger_path,
    next_legal_moment,
    paris_now,
    resolve_policy,
)

REQUEST_ID_RE = re.compile(r'^[A-Za-z0-9_.:-]{3,128}$')

DEFAULT_LISTEN = '127.0.0.1:8791'
ASTERISK_BIN = Path('/usr/sbin/asterisk')


def instance_data() -> dict[str, Any]:
    raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
    if not raw:
        raise VoiceBrokerDenied('SERGE_INSTANCE_FILE is required')
    try:
        return tomllib.loads(Path(raw).read_text(encoding='utf-8'))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise VoiceBrokerDenied('instance file unreadable') from exc


def asterisk_conf() -> Path:
    return config_root() / 'asterisk/asterisk.conf'


def asterisk_cli(*command: str, timeout: float = 10.0) -> tuple[int, str]:
    """Run `asterisk -C <conf> -rx '<command>'` as this user."""
    conf = asterisk_conf()
    if not ASTERISK_BIN.is_file():
        return 127, 'asterisk binary missing'
    if not conf.is_file():
        return 127, 'asterisk.conf missing'
    try:
        completed = subprocess.run(
            [str(ASTERISK_BIN), '-C', str(conf), '-rx', ' '.join(command)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 127, f'asterisk unreachable: {exc}'
    return completed.returncode, (completed.stdout + completed.stderr)[-2000:]


def trunk_status() -> dict[str, Any]:
    code, output = asterisk_cli('pjsip show registrations')
    registered = code == 0 and 'Registered' in output
    return {
        'asterisk_binary': ASTERISK_BIN.is_file(),
        'config_present': asterisk_conf().is_file(),
        'registration_checked': code == 0,
        'registered': registered,
        'detail': output[-300:] if output else '',
    }


def openai_key_present() -> bool:
    for name in ('openai-direct.env',):
        path = config_root() / f'secrets/{name}'
        if path.is_file():
            try:
                if path.read_text(encoding='utf-8').strip():
                    return True
            except OSError:
                continue
    return False


def originate(
    *,
    request_id: str,
    to_e164: str,
    purpose: str,
    task_id: str = '',
    message: str = '',
    ledger: VoiceLedger | None = None,
) -> dict[str, Any]:
    """Broker-gated originate. Returns the broker decision + dial result."""
    if not REQUEST_ID_RE.match(request_id):
        raise VoiceBrokerDenied('invalid request_id')
    if not E164_RE.match(to_e164):
        raise VoiceBrokerDenied('invalid recipient E.164')
    data = instance_data()
    identity = data.get('identity') or {}
    cli = str(identity.get('phone_voice_number') or '')
    active = ledger or VoiceLedger(default_ledger_path())
    policy = resolve_policy(system_root())
    decision = active.request_call(
        policy,
        request_id=request_id,
        to_e164=to_e164,
        cli=cli,
        purpose=purpose,
        task_id=task_id,
        message=message,
    )
    if decision['decision'] != 'allowed':
        return decision
    if decision.get('duplicate'):
        return decision
    trunk = trunk_status()
    if not trunk['registered']:
        active.record_outcome(decision['cdr_id'], outcome='originate_failed')
        return {
            **decision,
            'originated': False,
            'error': 'trunk_not_registered',
            'trunk': {k: v for k, v in trunk.items() if k != 'detail'},
        }
    code, output = asterisk_cli(
        'channel originate',
        f'Local/{to_e164}@serge-dial',
        'extension',
        f'{to_e164}@serge-campaign',
    )
    if code != 0:
        active.record_outcome(decision['cdr_id'], outcome='originate_failed')
        return {**decision, 'originated': False, 'error': output[-300:]}
    return {**decision, 'originated': True}


def health() -> dict[str, Any]:
    try:
        data = instance_data()
    except VoiceBrokerDenied as exc:
        return {'status': 'refused', 'error': str(exc)}
    features = data.get('features') or {}
    trunk = trunk_status() if features.get('phone_voice') else {}
    try:
        ledger = VoiceLedger(default_ledger_path())
        ledger_info = ledger.doctor()
    except OSError as exc:
        ledger_info = {'status': 'error', 'error': str(exc)}
    degraded: list[str] = []
    if features.get('phone_voice'):
        if not ASTERISK_BIN.is_file():
            degraded.append('asterisk_missing')
        if not asterisk_conf().is_file():
            degraded.append('asterisk_conf_missing')
        if not trunk.get('registered'):
            degraded.append('trunk_not_registered')
    return {
        'status': 'degraded' if degraded else 'ok',
        'degraded': degraded,
        'features': {
            'phone_voice': bool(features.get('phone_voice')),
            'voice': bool(features.get('voice')),
        },
        'trunk': trunk,
        'openai_tts': openai_key_present(),
        'ledger': ledger_info,
        'secret_values_included': False,
    }


# Un appel déjà en cours vers ce numéro : on réessaie dans 10 minutes.
BUSY_RETRY = timedelta(minutes=10)


def retry_at(reason: str) -> str:
    """Quand une demande refusée pour un temps pourra repartir, ou ``''``.

    Hors des heures d'appel : le prochain créneau (décision Q83) ; plafond
    du jour : minuit, heure de Paris ; un appel déjà en cours, ou Serge
    arrêté : dans 10 minutes. Un autre refus est définitif.
    """
    now = datetime.now(UTC)
    if reason == 'outside_legal_hours':
        hours = call_limits(default_canon_path())[2]
        return (
            next_legal_moment(paris_now(now), hours)
            .astimezone(UTC)
            .isoformat()
        )
    if reason == 'daily_quota_exceeded':
        tomorrow = paris_now(now) + timedelta(days=1)
        start = tomorrow.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(UTC).isoformat()
    if reason in ('already_in_progress', 'serge_arrete'):
        return (now + BUSY_RETRY).isoformat()
    return ''


def originate_for_task(payload: dict[str, Any]) -> dict[str, Any]:
    """Une demande d'appel du pipeline (``POST /originate``).

    Le numéro de la demande est tiré de l'envoi (``task_id``) et du nombre
    de demandes déjà faites pour lui : ``tou_3f2a.1``, ``tou_3f2a.2``… Le
    numéro de l'interlocuteur est remis en forme E.164. Un refus pour un
    temps dit quand réessayer (``retry_at``).
    """
    ledger = VoiceLedger(default_ledger_path())
    task_id = str(payload.get('task_id') or '')
    request_id = str(payload.get('request_id') or '')
    if task_id and not request_id:
        request_id = f'{task_id}.{len(ledger.calls_for_task(task_id)) + 1}'
    result = originate(
        request_id=request_id,
        to_e164=normalise_value('phone', str(payload.get('to') or '')),
        purpose=str(payload.get('purpose') or ''),
        task_id=task_id,
        message=str(payload.get('message') or ''),
        ledger=ledger,
    )
    if result['decision'] != 'allowed':
        result['retry_at'] = retry_at(str(result.get('reason') or ''))
    return result


class Handler(BaseHTTPRequestHandler):
    # Param name `format` matches BaseHTTPRequestHandler (Liskov).
    def log_message(self, format: str, *args: Any) -> None:  # noqa: N802, A002
        sys.stderr.write('voice-bridge: %s\n' % (format % args))

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
            info = health()
            self._send(200 if info['status'] == 'ok' else 503, info)
            return
        if parsed.path == '/calls':
            # Les demandes d'appel d'un envoi : confirmer qu'un appel est
            # parti, sans jamais le recomposer.
            query = urllib.parse.parse_qs(parsed.query)
            task_id = (query.get('task_id') or [''])[0]
            ledger = VoiceLedger(default_ledger_path())
            self._send(200, {'calls': ledger.calls_for_task(task_id)})
            return
        self._send(404, {'error': 'not_found'})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != '/originate':
            self._send(404, {'error': 'not_found'})
            return
        try:
            length = int(self.headers.get('Content-Length') or '0')
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            self._send(400, {'error': 'bad_length'})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(400, {'error': 'invalid_json'})
            return
        if not isinstance(payload, dict):
            self._send(400, {'error': 'invalid_payload'})
            return
        try:
            result = originate_for_task(payload)
        except VoiceBrokerDenied as exc:
            self._send(400, {'error': str(exc)})
            return
        if result['decision'] != 'allowed':
            self._send(403, result)
        elif not result.get('originated'):
            self._send(502, result)
        else:
            self._send(200, result)


def serve(listen: str = DEFAULT_LISTEN) -> int:
    from contextlib import closing

    from serge.db.store import default_canon_path, open_db
    from serge.voice.agent import close_interrupted_calls
    from serge.voice.s2s import start_audiosocket_thread

    with closing(open_db(default_canon_path())) as canon:
        close_interrupted_calls(canon)
    start_audiosocket_thread()
    host, _, port_raw = listen.rpartition(':')
    server = ThreadingHTTPServer(
        (host or '127.0.0.1', int(port_raw or '8791')),
        Handler,
    )
    sys.stderr.write(f'voice-bridge: écoute {listen}\n')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description='Serge voice bridge')
    sub = parser.add_subparsers(dest='command', required=True)
    serve_cmd = sub.add_parser('serve')
    serve_cmd.add_argument(
        '--listen',
        default=os.environ.get(
            'SERGE_VOICE_BRIDGE_LISTEN',
            DEFAULT_LISTEN,
        ),
    )
    orig = sub.add_parser('originate')
    orig.add_argument('--request-id', required=True)
    orig.add_argument('--to', required=True)
    orig.add_argument('--purpose', required=True)
    orig.add_argument('--task-id', default='')
    orig.add_argument('--message', default='')
    grant = sub.add_parser('consent-grant')
    grant.add_argument('--to', required=True)
    grant.add_argument(
        '--basis', required=True, choices=('contract', 'consent')
    )
    revoke = sub.add_parser('consent-revoke')
    revoke.add_argument('--to', required=True)
    block = sub.add_parser('block-add')
    block.add_argument('--to', required=True)
    block.add_argument('--reason', default='owner')
    unblock = sub.add_parser('block-remove')
    unblock.add_argument('--to', required=True)
    sub.add_parser('status')
    args = parser.parse_args(argv)
    try:
        if args.command == 'serve':
            return serve(args.listen)
        ledger = VoiceLedger(default_ledger_path())
        if args.command == 'originate':
            result = originate(
                request_id=args.request_id,
                to_e164=args.to,
                purpose=args.purpose,
                task_id=args.task_id,
                message=args.message,
                ledger=ledger,
            )
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0 if result.get('originated') else 1
        if args.command == 'consent-grant':
            print(
                json.dumps(ledger.grant_consent(args.to, args.basis), indent=2)
            )
        elif args.command == 'consent-revoke':
            print(json.dumps(ledger.revoke_consent(args.to), indent=2))
        elif args.command == 'block-add':
            print(json.dumps(ledger.block(args.to, args.reason), indent=2))
        elif args.command == 'block-remove':
            print(json.dumps(ledger.unblock(args.to), indent=2))
        elif args.command == 'status':
            print(json.dumps(health(), indent=2, ensure_ascii=False))
        else:
            raise AssertionError(args.command)
    except (VoiceBrokerDenied, OSError) as exc:
        print(json.dumps({'status': 'error', 'error': str(exc)}))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
