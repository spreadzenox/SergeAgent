#!/usr/bin/env python3
"""Environnement de test live-prudent (B8) : allowlist owner-only."""

from __future__ import annotations

import os
from typing import Any

from serge.e164 import is_valid, normalize
from serge.policy import PolicyError, is_test_env


def load_test_allowlist() -> dict[str, Any]:
    """Allowlist owner-only des tests live (B8). Depuis l'environnement.

    Seules ces destinations peuvent recevoir du trafic de test. Refuse
    une allowlist vide ou malformée (fail-closed).

    Returns:
        {emails: [...], sms: [...], discord_channel: str,
         discord_channel_id: str}.

    Raises:
        PolicyError: Si SERGE_ENV != test ou allowlist invalide.
    """
    if not is_test_env():
        raise PolicyError('allowlist test exige SERGE_ENV=test')
    emails = [
        item.strip().lower()
        for item in os.environ.get('SERGE_TEST_EMAILS', '').split(',')
        if item.strip()
    ]
    if not emails or any('@' not in item for item in emails):
        raise PolicyError('SERGE_TEST_EMAILS invalide (csv requis)')
    raw_sms = [
        normalize(item)
        for item in os.environ.get('SERGE_TEST_SMS', '').split(',')
        if item.strip()
    ]
    if not raw_sms or any(not is_valid(item) for item in raw_sms):
        raise PolicyError('SERGE_TEST_SMS invalide (E.164 requis)')
    channel = os.environ.get('SERGE_TEST_DISCORD_CHANNEL', '').strip()
    if not channel:
        raise PolicyError('SERGE_TEST_DISCORD_CHANNEL manquant')
    return {
        'emails': emails,
        'sms': raw_sms,
        'discord_channel': channel,
        'discord_channel_id': os.environ.get(
            'SERGE_TEST_DISCORD_CHANNEL_ID', ''
        ).strip(),
    }
