#!/usr/bin/env python3
"""Lecture AudioSocket au tempo 8 kHz (20 ms), pas en rafale.

Asterisk joue les TLV dès qu’ils arrivent. Un dump de 2 s en 50 ms
sonne « compressé ». File + horloge 20 ms ; silence si la file est vide.
"""

from __future__ import annotations

import socket
import threading

from serge.voice.audiosocket import encode

FRAME_8K = 320
FRAME_S = 0.02
SILENCE = b'\x00' * FRAME_8K


def take_frame(buf: bytearray) -> bytes | None:
    """Retire 20 ms de slin, ou None si la file est trop courte.

    Args:
        buf: File mutable.

    Returns:
        320 octets, ou None.
    """
    if len(buf) < FRAME_8K:
        return None
    frame = bytes(buf[:FRAME_8K])
    del buf[:FRAME_8K]
    return frame


class PhoneOut:
    """Envoie 20 ms de PCM toutes les 20 ms sur la socket Asterisk."""

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._lock = threading.Lock()
        self._buf = bytearray()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    @property
    def queued(self) -> int:
        """Octets encore en file (hors frame en cours)."""
        with self._lock:
            return len(self._buf)

    def push(self, slin: bytes) -> None:
        """Ajoute du slin 8 kHz à la file.

        Args:
            slin: PCM16 LE (reste court accepté).
        """
        if not slin:
            return
        with self._lock:
            self._buf.extend(slin)

    def close(self) -> None:
        """Arrête l’horloge (best effort)."""
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(FRAME_S):
            with self._lock:
                frame = take_frame(self._buf) or SILENCE
            try:
                self._sock.sendall(encode('audio', frame))
            except OSError:
                return
