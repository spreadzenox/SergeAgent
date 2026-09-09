#!/usr/bin/env python3
"""Consentements/blocklist voix dans le canon global (canal 'voice')."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from serge.db.store import utcnow
from serge.e164 import E164_RE
from serge.privacy import subject_hash
from serge.voice.policy import VoiceBrokerDenied

VOICE_CHANNEL = 'voice'


def _canon(canon_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(canon_path, timeout=30)


def grant_consent(
    canon_path: Path, to_e164: str, basis: str
) -> dict[str, Any]:
    if not E164_RE.match(to_e164):
        raise VoiceBrokerDenied('consent target must be E.164')
    if basis not in {'contract', 'consent'}:
        raise VoiceBrokerDenied('consent basis must be contract|consent')
    now = utcnow()
    digest = subject_hash(to_e164)
    connection = _canon(canon_path)
    try:
        connection.execute(
            'INSERT INTO consents(id, channel, subject_hash, subject_ref,'
            ' basis, granted_at, revoked_at) VALUES(?,?,?,?,?,?,?)'
            ' ON CONFLICT(channel, subject_hash) DO UPDATE SET'
            ' subject_ref=excluded.subject_ref, basis=excluded.basis,'
            " granted_at=excluded.granted_at, revoked_at=''",
            (
                f'voice_{digest}',
                VOICE_CHANNEL,
                digest,
                to_e164,
                basis,
                now,
                '',
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return {'status': 'granted', 'to_hash': digest, 'basis': basis}


def revoke_consent(canon_path: Path, to_e164: str) -> dict[str, Any]:
    now = utcnow()
    connection = _canon(canon_path)
    try:
        row = connection.execute(
            'UPDATE consents SET revoked_at=? WHERE channel=?'
            " AND subject_hash=? AND revoked_at=''",
            (now, VOICE_CHANNEL, subject_hash(to_e164)),
        )
        connection.commit()
    finally:
        connection.close()
    return {'status': 'revoked' if row.rowcount else 'unknown'}


def consent_basis(canon_path: Path, to_e164: str) -> str | None:
    connection = _canon(canon_path)
    try:
        row = connection.execute(
            'SELECT basis FROM consents WHERE subject_hash=?'
            " AND channel IN (?,?) AND revoked_at=''",
            (subject_hash(to_e164), VOICE_CHANNEL, '*'),
        ).fetchone()
    finally:
        connection.close()
    return str(row[0]) if row else None


def block(canon_path: Path, to_e164: str, reason: str) -> dict[str, Any]:
    if not E164_RE.match(to_e164):
        raise VoiceBrokerDenied('blocklist target must be E.164')
    now = utcnow()
    digest = subject_hash(to_e164)
    connection = _canon(canon_path)
    try:
        connection.execute(
            'INSERT INTO blocklist(id, channel, subject_hash, subject_ref,'
            ' reason, added_at) VALUES(?,?,?,?,?,?)'
            ' ON CONFLICT(channel, subject_hash) DO UPDATE SET'
            ' subject_ref=excluded.subject_ref, reason=excluded.reason,'
            ' added_at=excluded.added_at',
            (
                f'voice_{digest}',
                VOICE_CHANNEL,
                digest,
                to_e164,
                reason[:200],
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()
    return {'status': 'blocked', 'to_hash': digest}


def unblock(canon_path: Path, to_e164: str) -> dict[str, Any]:
    connection = _canon(canon_path)
    try:
        row = connection.execute(
            'DELETE FROM blocklist WHERE channel=? AND subject_hash=?',
            (VOICE_CHANNEL, subject_hash(to_e164)),
        )
        connection.commit()
    finally:
        connection.close()
    return {'status': 'unblocked' if row.rowcount else 'unknown'}


def is_blocked(canon_path: Path, to_e164: str) -> bool:
    connection = _canon(canon_path)
    try:
        row = connection.execute(
            'SELECT 1 FROM blocklist WHERE subject_hash=?'
            ' AND channel IN (?,?)',
            (subject_hash(to_e164), VOICE_CHANNEL, '*'),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def counts(canon_path: Path) -> dict[str, int]:
    connection = _canon(canon_path)
    try:
        consents = connection.execute(
            "SELECT COUNT(*) FROM consents WHERE channel=? AND revoked_at=''",
            (VOICE_CHANNEL,),
        ).fetchone()
        blocked = connection.execute(
            'SELECT COUNT(*) FROM blocklist WHERE channel=?',
            (VOICE_CHANNEL,),
        ).fetchone()
    finally:
        connection.close()
    return {'consents': int(consents[0]), 'blocklisted': int(blocked[0])}
