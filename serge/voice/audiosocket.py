#!/usr/bin/env python3
"""Protocole AudioSocket Asterisk (TLV). Encode / décode seulement."""

from __future__ import annotations

import struct
from typing import Literal

Kind = Literal['hangup', 'uuid', 'audio']

LISTEN_HOST = '127.0.0.1'
LISTEN_PORT = 8792
SESSION_UUID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'

_KINDS: dict[int, Kind] = {0x00: 'hangup', 0x01: 'uuid', 0x10: 'audio'}
_CODES: dict[Kind, int] = {name: code for code, name in _KINDS.items()}


class AudioSocketError(ValueError):
    """Trame TLV invalide (type inconnu, trop longue)."""


def encode(kind: Kind, payload: bytes = b'') -> bytes:
    """Encode un TLV (type + longueur réseau + payload).

    Args:
        kind: hangup | uuid | audio.
        payload: Octets utiles (slin ou UUID).

    Returns:
        La trame complète.

    Raises:
        AudioSocketError: Kind ou longueur invalides.
    """
    code = _CODES.get(kind)
    if code is None:
        raise AudioSocketError(f'PROTO: kind inconnu ({kind})')
    if len(payload) > 65535:
        raise AudioSocketError('PROTO: payload trop long')
    return bytes([code]) + struct.pack('!H', len(payload)) + payload


def decode_one(buffer: bytearray) -> tuple[Kind, bytes] | None:
    """Retire un TLV complet, ou None si incomplet.

    Args:
        buffer: Tampon mutable (consommé si complet).

    Returns:
        (kind, payload) ou None.

    Raises:
        AudioSocketError: Type d’octet inconnu.
    """
    if len(buffer) < 3:
        return None
    code = buffer[0]
    (length,) = struct.unpack('!H', bytes(buffer[1:3]))
    if len(buffer) < 3 + length:
        return None
    kind = _KINDS.get(code)
    if kind is None:
        raise AudioSocketError(f'PROTO: type inconnu (0x{code:02x})')
    payload = bytes(buffer[3 : 3 + length])
    del buffer[: 3 + length]
    return kind, payload
