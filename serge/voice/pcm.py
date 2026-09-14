#!/usr/bin/env python3
"""Rééchantillonnage linéaire PCM16 LE, 8 kHz ↔ 24 kHz (pas de numpy)."""

from __future__ import annotations

import array

RATIO = 3
SPEECH_RMS = 400


def upsample_8k_to_24k(slin8: bytes) -> bytes:
    """Passe 8 kHz → 24 kHz (3 samples interpolés par sample source).

    Args:
        slin8: PCM16 LE. Octet impair ignoré.

    Returns:
        PCM16 LE 24 kHz.
    """
    if len(slin8) % 2:
        slin8 = slin8[:-1]
    src = array.array('h')
    src.frombytes(slin8)
    if not src:
        return b''
    dst = array.array('h')
    last = len(src) - 1
    for index, sample in enumerate(src):
        nxt = src[index + 1] if index < last else sample
        step = (nxt - sample) // RATIO
        dst.append(sample)
        dst.append(sample + step)
        dst.append(sample + 2 * step)
    return dst.tobytes()


def downsample_24k_to_8k(pcm24: bytes) -> bytes:
    """Passe 24 kHz → 8 kHz (moyenne de 3 samples).

    Args:
        pcm24: PCM16 LE. Reste non multiple de 6 octets ignoré.

    Returns:
        PCM16 LE 8 kHz.
    """
    if len(pcm24) % 2:
        pcm24 = pcm24[:-1]
    src = array.array('h')
    src.frombytes(pcm24)
    dst = array.array('h')
    for index in range(0, len(src) - 2, RATIO):
        dst.append((src[index] + src[index + 1] + src[index + 2]) // RATIO)
    return dst.tobytes()


def is_speech(slin8: bytes, min_rms: int = SPEECH_RMS) -> bool:
    """Vrai si le slin 8 kHz dépasse le seuil RMS (bruit de ligne exclu).

    Args:
        slin8: PCM16 LE 8 kHz.
        min_rms: Seuil (défaut 400).

    Returns:
        True si parole probable.
    """
    if len(slin8) % 2:
        slin8 = slin8[:-1]
    src = array.array('h')
    src.frombytes(slin8)
    if not src:
        return False
    rms = int((sum(sample * sample for sample in src) / len(src)) ** 0.5)
    return rms >= min_rms
