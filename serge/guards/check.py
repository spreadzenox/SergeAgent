#!/usr/bin/env python3
"""check() : le point de passage unique avant toute exposition sortante.

Dans l'ordre : un canal connu (une ligne de ``canaux``), jamais deux fois
le même envoi, une adresse bloquée, l'accord exigé pour certains canaux,
le plafond de prises de contact en 30 jours (les premiers messages et les
relances, pas les réponses à un contact qui a écrit), les heures légales
pour la voix (hors de ces heures, le verdict dit quand l'appel pourra
partir). Chaque quota a un seul propriétaire : voix par jour dans le
broker voix ; ici, le plafond commun à tous les canaux.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import append_event, utcnow
from serge.guards.reasons import Reason, Verdict
from serge.policy import PolicyError
from serge.privacy import subject_hash
from serge.voice.policy import (
    VoiceBrokerDenied,
    call_hours,
    next_legal_moment,
    paris_now,
    within_legal_hours,
)


def _as_dt(moment: str) -> datetime:
    parsed = datetime.fromisoformat(moment)
    if parsed.tzinfo is None:
        raise PolicyError('guards.now doit être ISO avec fuseau')
    return parsed


def _zone_cap(policy: Mapping[str, Any], zone: str) -> int:
    try:
        zones = policy['calling_zones']
        cap = zones[zone or zones['default']]['contact_per_30d']
    except (KeyError, TypeError) as exc:
        raise PolicyError(
            'policy.calling_zones.<zone>.contact_per_30d requis'
        ) from exc
    if isinstance(cap, bool) or not isinstance(cap, (int, float)) or cap < 0:
        raise PolicyError('policy.contact_per_30d doit être un nombre >= 0')
    return int(cap)


def _opt_in_channels(policy: Mapping[str, Any]) -> list[str]:
    try:
        channels = policy['consent']['opt_in_channels']
    except (KeyError, TypeError) as exc:
        raise PolicyError('policy.consent.opt_in_channels requis') from exc
    if not isinstance(channels, list):
        raise PolicyError('policy.consent.opt_in_channels doit être une liste')
    return [str(item) for item in channels]


def check(
    connection: sqlite3.Connection,
    policy: Mapping[str, Any],
    action: Mapping[str, Any],
    now: str | None = None,
) -> Verdict:
    """Décide une exposition sortante + journalise (commit appelant).

    Args:
        connection: Connexion canon (écrit l'event verdict).
        policy: Policy validée (ou sous-ensemble : consent + calling_zones).
        action: channel, subject (l'adresse), idempotency_key (+ touch_id,
            l'envoi déjà écrit ; kind, ``reply`` pour une réponse ;
            contact_id, zone).
        now: ISO UTC (défaut : maintenant).

    Returns:
        Verdict fail-closed (allowed=False + code routable si doute).

    Raises:
        PolicyError: Policy ou horodatage malformé (fail-closed au boot).
    """
    moment = now or utcnow()
    verdict = _decide(connection, policy, action, moment)
    append_event(
        connection,
        actor='guards',
        type='guard',
        payload={
            'allowed': verdict.allowed,
            'code': verdict.reason.value,
            'channel': str(action.get('channel') or ''),
            'subject_hash': subject_hash(str(action.get('subject') or '')),
            'duplicate': verdict.duplicate,
            'retry_at': verdict.retry_at,
        },
    )
    return verdict


def _decide(
    connection: sqlite3.Connection,
    policy: Mapping[str, Any],
    action: Mapping[str, Any],
    moment: str,
) -> Verdict:
    """Décision pure (sans journal — voir check())."""
    current = _as_dt(moment)
    channel = str(action.get('channel') or '')
    known = connection.execute(
        'SELECT 1 FROM canaux WHERE id=?', (channel,)
    ).fetchone()
    if not known:
        return Verdict(False, Reason.UNKNOWN_CHANNEL)
    key = str(action.get('idempotency_key') or '')
    if not key:
        raise ValueError('guards.action.idempotency_key requis')
    # L'envoi est écrit avant de partir : il ne compte pas comme un doublon
    # de lui-même.
    seen = connection.execute(
        'SELECT 1 FROM touches WHERE idempotency_key=? AND id<>?',
        (key, str(action.get('touch_id') or '')),
    ).fetchone()
    if seen:
        return Verdict(False, Reason.DUPLICATE_IDEMPOTENT, duplicate=True)
    digest = subject_hash(str(action.get('subject') or ''))
    blocked = connection.execute(
        'SELECT 1 FROM blocklist WHERE subject_hash=? AND channel IN (?,?)',
        (digest, channel, '*'),
    ).fetchone()
    if blocked:
        return Verdict(False, Reason.BLOCKLISTED)
    if channel in _opt_in_channels(policy):
        granted = connection.execute(
            'SELECT 1 FROM consents WHERE subject_hash=? AND channel IN (?,?)'
            " AND revoked_at=''",
            (digest, channel, '*'),
        ).fetchone()
        if not granted:
            return Verdict(False, Reason.NO_CONSENT)
    contact_id = str(action.get('contact_id') or '')
    if contact_id and action.get('kind') != 'reply':
        cap = _zone_cap(policy, str(action.get('zone') or ''))
        since = (current - timedelta(days=30)).isoformat()
        count = connection.execute(
            'SELECT COUNT(*) FROM touches WHERE contact_id=?'
            " AND status='sent' AND kind<>'reply' AND created_at>=?",
            (contact_id, since),
        ).fetchone()[0]
        if int(count) >= cap:
            oldest = connection.execute(
                'SELECT MIN(created_at) FROM touches WHERE contact_id=?'
                " AND status='sent' AND kind<>'reply' AND created_at>=?",
                (contact_id, since),
            ).fetchone()[0]
            retry = ''
            if oldest:
                retry = (
                    datetime.fromisoformat(str(oldest)) + timedelta(days=30)
                ).isoformat()
            return Verdict(False, Reason.QUOTA_CONTACT_30D, retry_at=retry)
    if channel == 'voice':
        try:
            paris = paris_now(current)
            hours = call_hours(policy)
        except VoiceBrokerDenied as exc:
            raise PolicyError('fuseau Europe/Paris indisponible') from exc
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError('policy.calling_zones : heures d’appel') from exc
        if not within_legal_hours(paris, hours):
            # L'appel attend le prochain créneau (décision Q83).
            later = next_legal_moment(paris, hours).astimezone(current.tzinfo)
            return Verdict(
                False, Reason.OUTSIDE_WINDOW, retry_at=later.isoformat()
            )
    return Verdict(True, Reason.OK)
