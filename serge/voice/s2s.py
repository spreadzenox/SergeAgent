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
    encode,
)
from serge.voice.pcm import (
    downsample_24k_to_8k,
    is_speech,
    upsample_8k_to_24k,
)
from serge.voice.providers import SYSTEM_PROMPT, secrets
from serge.voice.realtime import DEFAULT_MODELS, RealtimeCall, RealtimeError

Provider = Literal['xai', 'openai']
PROVIDER_ORDER: tuple[Provider, ...] = ('xai', 'openai')
POLL_S = 0.05
MAX_CALL_S = 180.0
KEEPALIVE_S = 0.4
MIC_OPEN_S = 4.0
OPENING = 'Dis bonjour en une phrase, puis écoute.'
SILENCE_FRAME = encode('audio', b'\x00' * 320)


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


def _push_phone(
    sock: socket.socket,
    leftover: bytes,
    b64: str,
    lock: threading.Lock,
) -> bytes:
    try:
        pcm24 = leftover + base64.b64decode(b64)
    except ValueError:
        return leftover
    keep = len(pcm24) % 6
    ready, rest = pcm24[: len(pcm24) - keep], pcm24[len(pcm24) - keep :]
    slin = downsample_24k_to_8k(ready)
    if slin:
        with lock:
            sock.sendall(encode('audio', slin))
    return rest


def _hold(
    sock: socket.socket, lock: threading.Lock, stop: threading.Event
) -> None:
    """Silence 20 ms toutes les 0,4 s (Asterisk coupe à 2 s sans PCM)."""
    while not stop.wait(KEEPALIVE_S):
        try:
            with lock:
                sock.sendall(SILENCE_FRAME)
        except OSError:
            return


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
    lock = threading.Lock()
    stop = threading.Event()
    with lock:
        ast.sendall(SILENCE_FRAME)
    threading.Thread(target=_hold, args=(ast, lock, stop), daemon=True).start()
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
        mic_on = False
        chunks = 0
        deadline = opened + max_s
        while time.monotonic() < deadline:
            if not mic_on and time.monotonic() - opened >= MIC_OPEN_S:
                mic_on = True
            ready, _, _ = select.select([ast], [], [], POLL_S)
            if ast in ready:
                for kind, payload in _pull_ast(ast, buf):
                    if kind == 'hangup':
                        sys.stderr.write(f'voice-s2s: audio {chunks}\n')
                        return
                    if (
                        kind == 'audio'
                        and payload
                        and mic_on
                        and is_speech(payload)
                    ):
                        pcm = upsample_8k_to_24k(payload)
                        if pcm:
                            call.send_audio(
                                base64.b64encode(pcm).decode('ascii')
                            )
            try:
                actions = call.poll()
            except RealtimeError as exc:
                if 'time' in str(exc).lower():
                    continue
                raise
            for kind, value in actions:
                if kind == 'done':
                    mic_on = True
                if kind == 'audio' and value:
                    leftover = _push_phone(ast, leftover, str(value), lock)
                    chunks += 1
    finally:
        stop.set()
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
