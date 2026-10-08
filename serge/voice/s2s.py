#!/usr/bin/env python3
"""Pont AudioSocket ↔ Realtime : l'agent vocal en direct.

Au décrochage, l'UUID d'AudioSocket dit le sens et le numéro de l'appel :
l'appel devient une tâche de l'agent vocal réglé en base
(``serge/voice/agent.py``), avec son prompt, la fiche du contact et ses
outils. Pendant l'appel, les outils demandés sont exécutés ; à la fin, la
transcription des deux voix entre dans le fil du contact. Repli : socket
fermée → AGI turn.py. Pas de secret en log.
"""

from __future__ import annotations

import base64
import select
import socket
import sqlite3
import sys
import threading
import time

from serge.coupe_circuit import serge_demarre
from serge.db.store import default_canon_path, open_db
from serge.interpreter.intro import serge_text
from serge.voice.agent import (
    Call,
    finish_call,
    hear,
    instructions,
    peer_from_uuid,
    run_tool_call,
    settings,
    start_call,
    tools,
)
from serge.voice.audiosocket import (
    LISTEN_HOST,
    LISTEN_PORT,
    AudioSocketError,
    decode_one,
)
from serge.voice.ledger import VoiceLedger
from serge.voice.pcm import is_speech, to_model_rate, to_phone_rate
from serge.voice.phoneout import PhoneOut
from serge.voice.policy import default_ledger_path
from serge.voice.providers import secrets
from serge.voice.realtime import PROVIDERS, RealtimeCall, RealtimeError

POLL_S = 0.05
MIC_OPEN_S = 6.0
COMMIT_S = 1.2


def open_session(
    keys: dict[str, str],
    prompt: str = '',
    agent_tools: list[dict[str, object]] | None = None,
    cfg: dict[str, str] | None = None,
) -> RealtimeCall:
    """Ouvre le premier fournisseur joignable. Refuse sans clé utilisable.

    L'ordre des fournisseurs, leurs modèles et leurs voix sont des réglages
    de l'agent vocal en base (``fournisseurs`` : ``xai,openai`` ;
    ``modele_xai``, ``voix_xai``…). Un fournisseur sans modèle réglé est
    passé.

    Args:
        keys: Sortie de secrets() (openai / xai).
        prompt: Les instructions de l'agent.
        agent_tools: Les outils qu'il peut appeler.
        cfg: Ses réglages.

    Returns:
        Session Realtime prête.

    Raises:
        RealtimeError: Aucun provider joignable.
    """
    cfg = cfg or {}
    wanted = [p.strip() for p in cfg.get('fournisseurs', '').split(',')]
    last = 'PROVIDER: clé manquante'
    for name in (p for p in wanted if p in PROVIDERS):
        key = keys.get(name) or ''
        model = cfg.get(f'modele_{name}') or ''
        if not key or not model:
            continue
        try:
            return RealtimeCall.dial(
                name,
                key,
                model,
                prompt,
                voice=cfg.get(f'voix_{name}') or '',
                timeout=8.0,
                tools=agent_tools,
            )
        except RealtimeError:
            last = f'PROVIDER: {name} indisponible'
    raise RealtimeError(last)


def _first_uuid(ast: socket.socket, buf: bytearray) -> bytes:
    """L'UUID qu'AudioSocket envoie en premier (le sens et le numéro)."""
    ast.settimeout(2.0)
    while True:
        for kind, payload in _pull_ast(ast, buf):
            if kind == 'uuid':
                return payload
            if kind == 'hangup':
                return b''


def _begin(
    canon: sqlite3.Connection, ledger: VoiceLedger, raw_uuid: bytes
) -> tuple[Call, str]:
    """La tâche de l'appel et son numéro dans le journal des appels.

    Raises:
        RealtimeError: Pas d'agent vocal en base (repli : AGI turn.py).
    """
    direction, phone = peer_from_uuid(raw_uuid)
    if direction == 'outbound':
        claim = ledger.claim_outbound(phone) or {}
        cdr_id, touch_id = (
            str(claim.get('cdr_id') or ''),
            str(claim.get('task_id') or ''),
        )
    else:
        cdr_id = ledger.record_inbound(caller=phone or 'inconnu', did='')[
            'cdr_id'
        ]
        touch_id = ''
    call = start_call(canon, direction or 'inbound', phone, cdr_id, touch_id)
    if call is None:
        raise RealtimeError('AGENT: aucun agent vocal allumé en base')
    return call, cdr_id


def _pull_ast(sock: socket.socket, buf: bytearray) -> list[tuple[str, bytes]]:
    chunk = sock.recv(4096)
    if not chunk:
        return [('hangup', b'')]
    buf.extend(chunk)
    out: list[tuple[str, bytes]] = []
    while True:
        msg = decode_one(buf)
        if msg is None:
            break
        out.append(msg)
    return out


def _queue_phone(out: PhoneOut, leftover: bytes, b64: str, rate: int) -> bytes:
    try:
        chunk = base64.b64decode(b64)
    except ValueError:
        return leftover
    slin, rest = to_phone_rate(chunk, leftover, rate)
    out.push(slin)
    return rest


def pump(ast: socket.socket, max_s: float | None = None) -> None:
    """Pompe AudioSocket ↔ Realtime jusqu’au hangup ou timeout.

    Args:
        ast: Socket acceptée (Asterisk).
        max_s: Plafond d’appel (sinon le réglage de l'agent en base).

    Raises:
        RealtimeError: Pas de session (fermeture → AGI).
        AudioSocketError: TLV invalide.
    """
    buf = bytearray()
    canon = open_db(default_canon_path())
    ledger = VoiceLedger(default_ledger_path())
    try:
        agent, cdr_id = _begin(canon, ledger, _first_uuid(ast, buf))
    except BaseException:
        canon.close()
        raise
    cfg = settings(canon, agent)
    limit = max_s or float(cfg.get('duree_max_secondes') or 0)
    ast.settimeout(POLL_S)
    out = PhoneOut(ast)
    call = None
    leftover = b''
    opened = time.monotonic()
    try:
        call = open_session(
            secrets(), instructions(canon, agent), tools(canon, agent), cfg
        )
        call.ws.sock.settimeout(POLL_S)
        sys.stderr.write(
            f'voice-s2s: session {getattr(call, "provider", "?")}\n'
        )
        call.inject_text(serge_text(canon, 'voice_opening'))
        greeting_done = False
        chunks = 0
        mic_n = 0
        last_voice = 0.0
        need_commit = False
        raw_rate = getattr(call, 'pcm_rate', 24000)
        rate = raw_rate if isinstance(raw_rate, int) else 24000
        deadline = opened + limit
        while time.monotonic() < deadline:
            now = time.monotonic()
            aged = now - opened >= MIC_OPEN_S
            mic_on = (greeting_done or aged) and out.queued < 640
            if (
                mic_on
                and need_commit
                and last_voice
                and now - last_voice > COMMIT_S
            ):
                try:
                    call.commit_turn()
                except RealtimeError:
                    pass
                need_commit = False
            ready, _, _ = select.select([ast], [], [], POLL_S)
            if ast in ready:
                for kind, payload in _pull_ast(ast, buf):
                    if kind == 'hangup':
                        sys.stderr.write(
                            f'voice-s2s: audio {chunks} mic {mic_n}\n'
                        )
                        return
                    if kind == 'audio' and payload and mic_on:
                        pcm = to_model_rate(payload, rate)
                        if pcm:
                            call.send_audio(
                                base64.b64encode(pcm).decode('ascii')
                            )
                            mic_n += 1
                        if is_speech(payload):
                            last_voice = now
                            need_commit = True
            try:
                actions = call.poll()
            except RealtimeError as exc:
                if 'time' in str(exc).lower():
                    continue
                raise
            for kind, value in actions:
                if kind == 'done':
                    greeting_done = True
                    need_commit = False
                if kind == 'transcript' and value:
                    hear(agent, 'Serge', str(value))
                if kind == 'heard' and value:
                    hear(agent, 'Contact', str(value))
                if kind == 'tool':
                    call.send_tool_output(
                        value['call_id'],
                        run_tool_call(
                            canon, agent, value['name'], value['arguments']
                        ),
                    )
                if kind == 'audio' and value:
                    leftover = _queue_phone(out, leftover, str(value), rate)
                    chunks += 1
    finally:
        try:
            if cdr_id:
                ledger.record_outcome(
                    cdr_id,
                    outcome='completed',
                    duration_s=int(time.monotonic() - opened),
                    transcript='\n'.join(agent.lines),
                )
            finish_call(canon, agent)
        except Exception as exc:  # noqa: BLE001 — l'appel est fini, le journal suit
            sys.stderr.write(f'voice-s2s: clore {type(exc).__name__}\n')
        canon.close()
        out.close()
        if call is not None:
            call.close()
        ast.close()


def handle_call(conn: socket.socket) -> None:
    """Un appel arrivé par AudioSocket : l'agent vocal, si Serge est démarré.

    Serge arrêté dans Mission Control : aucun modèle ne parle, la socket est
    fermée et Asterisk passe à la suite du plan d'appel, qui raccroche aussi.
    """
    if not serge_demarre():
        sys.stderr.write('voice-s2s: Serge arrêté, appel refusé\n')
        conn.close()
        return
    try:
        pump(conn)
    except (RealtimeError, AudioSocketError, OSError) as exc:
        sys.stderr.write(f'voice-s2s: fin ({type(exc).__name__})\n')
        try:
            conn.close()
        except OSError:
            pass


def start_audiosocket_thread() -> None:
    """Listener daemon :8792. Bind raté = log, HTTP survit."""

    def run() -> None:
        try:
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind((LISTEN_HOST, LISTEN_PORT))
            server.listen(4)
            sys.stderr.write(
                f'voice-s2s: AudioSocket {LISTEN_HOST}:{LISTEN_PORT}\n'
            )
            while True:
                conn, _ = server.accept()
                sys.stderr.write('voice-s2s: appel\n')
                threading.Thread(
                    target=handle_call, args=(conn,), daemon=True
                ).start()
        except OSError as exc:
            sys.stderr.write(f'voice-s2s: écoute impossible ({exc})\n')

    threading.Thread(target=run, daemon=True).start()
