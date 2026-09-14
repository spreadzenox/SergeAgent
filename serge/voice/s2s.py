#!/usr/bin/env python3
"""Pont AudioSocket ↔ Realtime (P5 voice_dialog).

LLM-B, checklist 4/4 (parole libre, réponse ouverte, contexte,
formulations). Repli : socket fermée → AGI turn.py. Pas de secret en log.
"""

from __future__ import annotations

import base64
import select
import socket
import sys
import threading
import time
from typing import Literal

from serge.voice.audiosocket import (
    LISTEN_HOST,
    LISTEN_PORT,
    AudioSocketError,
    decode_one,
)
from serge.voice.pcm import is_speech, to_model_rate, to_phone_rate
from serge.voice.phoneout import PhoneOut
from serge.voice.providers import SYSTEM_PROMPT, secrets
from serge.voice.realtime import DEFAULT_MODELS, RealtimeCall, RealtimeError

Provider = Literal['xai', 'openai']
PROVIDER_ORDER: tuple[Provider, ...] = ('xai', 'openai')
POLL_S = 0.05
MAX_CALL_S = 180.0
MIC_OPEN_S = 6.0
COMMIT_S = 1.2
OPENING = 'Dis bonjour en une phrase, puis écoute.'


def open_session(keys: dict[str, str]) -> RealtimeCall:
    """Ouvre xAI puis OpenAI. Refuse sans clé utilisable.

    Args:
        keys: Sortie de secrets() (openai / xai).

    Returns:
        Session Realtime prête.

    Raises:
        RealtimeError: Aucun provider joignable.
    """
    last = 'PROVIDER: clé manquante'
    for name in PROVIDER_ORDER:
        key = keys.get(name) or ''
        if not key:
            continue
        try:
            return RealtimeCall.dial(
                name, key, DEFAULT_MODELS[name], SYSTEM_PROMPT, timeout=8.0
            )
        except RealtimeError:
            last = f'PROVIDER: {name} indisponible'
    raise RealtimeError(last)


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


def pump(ast: socket.socket, max_s: float = MAX_CALL_S) -> None:
    """Pompe AudioSocket ↔ Realtime jusqu’au hangup ou timeout.

    Args:
        ast: Socket acceptée (Asterisk).
        max_s: Plafond d’appel.

    Raises:
        RealtimeError: Pas de session (fermeture → AGI).
        AudioSocketError: TLV invalide.
    """
    ast.settimeout(POLL_S)
    out = PhoneOut(ast)
    call = None
    leftover = b''
    buf = bytearray()
    try:
        call = open_session(secrets())
        call.ws.sock.settimeout(POLL_S)
        sys.stderr.write(
            f'voice-s2s: session {getattr(call, "provider", "?")}\n'
        )
        call.inject_text(OPENING)
        opened = time.monotonic()
        greeting_done = False
        chunks = 0
        mic_n = 0
        last_voice = 0.0
        need_commit = False
        raw_rate = getattr(call, 'pcm_rate', 24000)
        rate = raw_rate if isinstance(raw_rate, int) else 24000
        deadline = opened + max_s
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
                if kind == 'audio' and value:
                    leftover = _queue_phone(out, leftover, str(value), rate)
                    chunks += 1
    finally:
        out.close()
        if call is not None:
            call.close()
        ast.close()


def start_audiosocket_thread() -> None:
    """Listener daemon :8792. Bind raté = log, HTTP survit."""

    def handle(conn: socket.socket) -> None:
        try:
            pump(conn)
        except (RealtimeError, AudioSocketError, OSError) as exc:
            sys.stderr.write(f'voice-s2s: fin ({type(exc).__name__})\n')
            try:
                conn.close()
            except OSError:
                pass

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
                    target=handle, args=(conn,), daemon=True
                ).start()
        except OSError as exc:
            sys.stderr.write(f'voice-s2s: écoute impossible ({exc})\n')

    threading.Thread(target=run, daemon=True).start()
