#!/usr/bin/env python3
"""Normaliseurs : physique du canal → signaux universels. Tables, pas de if.

Règle de sur-classement : en cas de doute, vers le haut (faux positif =
centimes, faux négatif = vente perdue). Inconnu → OTHER (file d'examen),
jamais jeté. v1 : email + voix (autres canaux avec leurs adaptateurs).
"""

from __future__ import annotations

from serge.observe.signals import Signal

TABLES: dict[str, dict[str, Signal]] = {
    'email': {
        'RECEIVED': Signal.REPLIED,
        'BOUNCED': Signal.TECH_FAIL,
        'COMPLAINED': Signal.OPT_OUT,
        'OPENED': Signal.SEEN,
        'CLICKED': Signal.ENGAGED,
    },
    'voice': {
        'MISSED': Signal.SEEN,
        'CONNECTED': Signal.ENGAGED,
        'VOICEMAIL_LEFT': Signal.ENGAGED,
        'TRANSCRIPT': Signal.REPLIED,
        'DTMF_1': Signal.INTENT,
        'CALLBACK_REQUESTED': Signal.INTENT,
        'NUMBER_INVALID': Signal.TECH_FAIL,
    },
}


def normalize(channel: str, native_type: str) -> Signal:
    """Mappe un événement natif vers le signal universel.

    Args:
        channel: Canal (email, voice...).
        native_type: Type natif du canal (RECEIVED, BOUNCED...).

    Returns:
        Le signal (OTHER si canal ou type inconnu).
    """
    table = TABLES.get(channel)
    if table is None:
        return Signal.OTHER
    return table.get(native_type, Signal.OTHER)
