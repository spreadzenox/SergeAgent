#!/usr/bin/env python3
"""Verified, idempotent inbound SMS broker. Outbound SMS is intentionally absent."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class SmsBrokerDenied(ValueError):
    pass


OTP_RE = re.compile(r'(?<!\d)(\d{4,8})(?!\d)')


def _verify(payload: bytes, signature: str, secret: bytes) -> None:
    if len(secret) < 16 or not re.fullmatch(r'[a-f0-9]{64}', signature):
        raise SmsBrokerDenied('SMS signature invalid')
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise SmsBrokerDenied('SMS signature invalid')


class SmsInbox:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)
        try:
            connection.execute("""CREATE TABLE IF NOT EXISTS inbound_sms (
                provider_message_id TEXT PRIMARY KEY, sender_hash TEXT NOT NULL,
                body_hash TEXT NOT NULL, purpose TEXT NOT NULL, otp TEXT,
                received_at TEXT NOT NULL, signature_verified INTEGER NOT NULL
            )""")
            connection.commit()
        finally:
            connection.close()

    def ingest(
        self, payload: bytes, signature: str, secret: bytes, *, purpose: str
    ) -> dict[str, Any]:
        if purpose not in {
            'ACCOUNT_VERIFICATION',
            'LOGIN_RECOVERY',
            'OBSERVATION',
        }:
            raise SmsBrokerDenied('SMS purpose not authorized')
        _verify(payload, signature, secret)
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SmsBrokerDenied('SMS payload invalid') from exc
        if not isinstance(value, dict) or set(value) != {
            'id',
            'from',
            'body',
            'received_at',
        }:
            raise SmsBrokerDenied('SMS envelope invalid')
        message_id, sender, body, received_at = (
            value[k] for k in ('id', 'from', 'body', 'received_at')
        )
        if not all(
            isinstance(item, str) and item
            for item in (message_id, sender, body, received_at)
        ):
            raise SmsBrokerDenied('SMS fields invalid')
        if (
            not re.fullmatch(r'[A-Za-z0-9_.:-]{3,255}', message_id)
            or len(body) > 2000
        ):
            raise SmsBrokerDenied('SMS content invalid')
        try:
            datetime.fromisoformat(
                received_at.replace('Z', '+00:00')
            ).astimezone(UTC)
        except ValueError as exc:
            raise SmsBrokerDenied('SMS timestamp invalid') from exc
        match = (
            OTP_RE.search(body)
            if purpose in {'ACCOUNT_VERIFICATION', 'LOGIN_RECOVERY'}
            else None
        )
        otp = match.group(1) if match else None
        row = (
            message_id,
            hashlib.sha256(sender.encode()).hexdigest(),
            hashlib.sha256(body.encode()).hexdigest(),
            purpose,
            otp,
            received_at,
            1,
        )
        connection = sqlite3.connect(self.db_path, timeout=30)
        try:
            existing = connection.execute(
                'SELECT body_hash,purpose,otp FROM inbound_sms WHERE provider_message_id=?',
                (message_id,),
            ).fetchone()
            if existing:
                if existing[0] != row[2] or existing[1] != purpose:
                    raise SmsBrokerDenied('Divergent SMS replay')
                return {
                    'status': 'duplicate',
                    'provider_message_id': message_id,
                    'otp': existing[2],
                }
            connection.execute(
                'INSERT INTO inbound_sms VALUES (?,?,?,?,?,?,?)', row
            )
            connection.commit()
        finally:
            connection.close()
        return {
            'status': 'accepted',
            'provider_message_id': message_id,
            'purpose': purpose,
            'otp': otp,
            'raw_body_stored': False,
            'sender_stored': False,
            'signature_verified': True,
            'outbound_sms_enabled': False,
        }

    def latest_otp(self, purpose: str = 'ACCOUNT_VERIFICATION') -> str | None:
        """Return the newest stored OTP. Raw SMS bodies are not retained."""
        connection = sqlite3.connect(self.db_path, timeout=30)
        try:
            row = connection.execute(
                'SELECT otp FROM inbound_sms WHERE purpose=? AND otp IS NOT NULL '
                'ORDER BY received_at DESC LIMIT 1',
                (purpose,),
            ).fetchone()
        finally:
            connection.close()
        if row is None or not row[0]:
            return None
        return str(row[0])
