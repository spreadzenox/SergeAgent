#!/usr/bin/env python3
"""Voice CDR ledger (calls) + consent/blocklist via le canon global."""

from __future__ import annotations

import hashlib
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from serge.db.store import default_canon_path, open_db
from serge.e164 import E164_RE
from serge.voice.consents import (
    block as _canon_block,
)
from serge.voice.consents import (
    consent_basis as _canon_basis,
)
from serge.voice.consents import (
    counts as _canon_counts,
)
from serge.voice.consents import (
    grant_consent as _canon_grant,
)
from serge.voice.consents import (
    is_blocked as _canon_is_blocked,
)
from serge.voice.consents import (
    revoke_consent as _canon_revoke,
)
from serge.voice.consents import (
    unblock as _canon_unblock,
)
from serge.voice.policy import (
    VoiceBrokerDenied,
    VoicePolicy,
    paris_now,
    within_legal_hours,
)

MAX_PER_RECIPIENT_30D = 4
PURPOSES = frozenset({'prospection', 'contract', 'callback', 'test'})
PENDING_CLAIM_SECONDS = 600


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class VoiceLedger:
    """CDR voix + consent/blocklist (canon global, canal 'voice'). 0600."""

    def __init__(self, db_path: Path, canon_path: Path | None = None):
        self.db_path = db_path
        self.canon_path = canon_path or default_canon_path()
        fresh = not db_path.exists()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=30)
        try:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS calls (
                    request_id TEXT PRIMARY KEY, cdr_id TEXT NOT NULL,
                    direction TEXT NOT NULL, to_e164 TEXT NOT NULL,
                    to_hash TEXT NOT NULL, cli TEXT NOT NULL,
                    purpose TEXT NOT NULL, task_id TEXT NOT NULL,
                    decision TEXT NOT NULL, reason TEXT NOT NULL,
                    created_at TEXT NOT NULL, outcome TEXT NOT NULL DEFAULT 'pending',
                    duration_s INTEGER NOT NULL DEFAULT 0,
                    recording_path TEXT NOT NULL DEFAULT '',
                    callback_requested INTEGER NOT NULL DEFAULT 0,
                    claimed_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS outbound_messages (
                    request_id TEXT PRIMARY KEY, message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            connection.commit()
        finally:
            connection.close()
        if fresh:
            try:
                db_path.chmod(0o600)
            except OSError:
                pass
        canon = open_db(self.canon_path)
        canon.close()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=30)

    def grant_consent(self, to_e164: str, basis: str) -> dict[str, Any]:
        return _canon_grant(self.canon_path, to_e164, basis)

    def revoke_consent(self, to_e164: str) -> dict[str, Any]:
        return _canon_revoke(self.canon_path, to_e164)

    def consent_basis(self, to_e164: str) -> str | None:
        return _canon_basis(self.canon_path, to_e164)

    def block(self, to_e164: str, reason: str) -> dict[str, Any]:
        return _canon_block(self.canon_path, to_e164, reason)

    def unblock(self, to_e164: str) -> dict[str, Any]:
        return _canon_unblock(self.canon_path, to_e164)

    def is_blocked(self, to_e164: str) -> bool:
        return _canon_is_blocked(self.canon_path, to_e164)

    def _count_allowed(
        self,
        connection: sqlite3.Connection,
        to_hash: str | None,
        since: str,
    ) -> int:
        if to_hash is None:
            row = connection.execute(
                "SELECT COUNT(*) FROM calls WHERE direction='outbound'"
                " AND decision='allowed' AND created_at>=?",
                (since,),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT COUNT(*) FROM calls WHERE direction='outbound'"
                " AND decision='allowed' AND to_hash=? AND created_at>=?",
                (to_hash, since),
            ).fetchone()
        return int(row[0]) if row else 0

    def counts(
        self, to_e164: str, now: datetime | None = None
    ) -> dict[str, int]:
        moment = paris_now(now)
        day_start = moment.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = moment - timedelta(days=30)
        connection = self._connect()
        try:
            return {
                'today': self._count_allowed(
                    connection,
                    None,
                    day_start.astimezone(UTC).isoformat(),
                ),
                'recipient_30d': self._count_allowed(
                    connection,
                    _hash(to_e164),
                    month_start.astimezone(UTC).isoformat(),
                ),
            }
        finally:
            connection.close()

    def in_progress(self, to_e164: str) -> bool:
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT 1 FROM calls WHERE direction='outbound'"
                " AND to_hash=? AND decision='allowed' AND outcome='pending'",
                (_hash(to_e164),),
            ).fetchone()
        finally:
            connection.close()
        return row is not None

    def request_call(
        self,
        policy: VoicePolicy,
        *,
        request_id: str,
        to_e164: str,
        cli: str,
        purpose: str,
        task_id: str = '',
        message: str = '',
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """Decide an outbound call. Denials are recorded, never raised."""
        created = (now or datetime.now(UTC)).astimezone(UTC)
        created_iso = created.isoformat()
        cdr_id = (
            f'cdr_{created.strftime("%Y%m%dT%H%M%S")}_{_hash(request_id)[:12]}'
        )
        connection = self._connect()
        try:
            prior = connection.execute(
                'SELECT decision,reason,cdr_id,to_e164,cli,purpose'
                ' FROM calls WHERE request_id=?',
                (request_id,),
            ).fetchone()
            if prior:
                if (prior[3], prior[4], prior[5]) != (to_e164, cli, purpose):
                    raise VoiceBrokerDenied('divergent voice replay')
                return {
                    'decision': prior[0],
                    'reason': prior[1],
                    'cdr_id': prior[2],
                    'request_id': request_id,
                    'duplicate': True,
                }
            reason = self._decide(
                connection,
                policy,
                to_e164,
                cli,
                purpose,
                created,
            )
            decision = 'allowed' if reason == 'allowed' else 'denied'
            connection.execute(
                'INSERT INTO calls(request_id,cdr_id,direction,to_e164,to_hash,cli,'
                'purpose,task_id,decision,reason,created_at)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (
                    request_id,
                    cdr_id,
                    'outbound',
                    to_e164,
                    _hash(to_e164),
                    cli,
                    purpose,
                    task_id[:200],
                    decision,
                    reason,
                    created_iso,
                ),
            )
            if decision == 'allowed' and message:
                connection.execute(
                    'INSERT OR REPLACE INTO outbound_messages(request_id,message,created_at)'
                    ' VALUES(?,?,?)',
                    (request_id, message[:2000], created_iso),
                )
            connection.commit()
        finally:
            connection.close()
        return {
            'decision': decision,
            'reason': reason,
            'cdr_id': cdr_id,
            'request_id': request_id,
            'duplicate': False,
        }

    def _decide(
        self,
        connection: sqlite3.Connection,
        policy: VoicePolicy,
        to_e164: str,
        cli: str,
        purpose: str,
        created: datetime,
    ) -> str:
        if not E164_RE.match(to_e164):
            return 'invalid_recipient_e164'
        if purpose not in PURPOSES:
            return 'invalid_purpose'
        if policy.mode == 'sandbox':
            return 'sandbox_no_outbound'
        if policy.kill_switch:
            return 'kill_switch_active'
        if not policy.external_actions:
            return 'external_actions_disabled'
        if not policy.mandate_outbound_allowed:
            return 'mandate_deny'
        if not policy.cli_expected or cli != policy.cli_expected:
            return 'cli_not_locked_npv'
        if self.is_blocked(to_e164):
            return 'blocklisted'
        if self.consent_basis(to_e164) is None:
            return 'no_consent_or_contract'
        try:
            paris = paris_now(created)
        except VoiceBrokerDenied:
            return 'timezone_unavailable'
        if not within_legal_hours(paris):
            return 'outside_legal_hours'
        day_start = paris.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = paris - timedelta(days=30)
        if (
            self._count_allowed(
                connection,
                None,
                day_start.astimezone(UTC).isoformat(),
            )
            >= policy.max_calls_per_day
        ):
            return 'daily_quota_exceeded'
        if (
            self._count_allowed(
                connection,
                _hash(to_e164),
                month_start.astimezone(UTC).isoformat(),
            )
            >= MAX_PER_RECIPIENT_30D
        ):
            return 'recipient_quota_4_per_30d'
        if self.in_progress(to_e164):
            return 'already_in_progress'
        return 'allowed'

    def claim_outbound(
        self,
        to_e164: str,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Claim the newest allowed, unclaimed outbound for the AGI leg."""
        connection = self._connect()
        try:
            row = connection.execute(
                'SELECT request_id,cdr_id,task_id,purpose,created_at'
                " FROM calls WHERE direction='outbound' AND to_hash=?"
                " AND decision='allowed' AND outcome='pending' AND claimed_at=''"
                ' ORDER BY created_at DESC LIMIT 1',
                (_hash(to_e164),),
            ).fetchone()
            if not row:
                return None
            try:
                created = datetime.fromisoformat(row[4])
            except ValueError:
                return None
            moment = (now or datetime.now(UTC)).astimezone(UTC)
            age = moment - created.astimezone(UTC)
            if age.total_seconds() > PENDING_CLAIM_SECONDS:
                return None
            now_iso = moment.isoformat()
            connection.execute(
                'UPDATE calls SET claimed_at=? WHERE request_id=?',
                (now_iso, row[0]),
            )
            message_row = connection.execute(
                'SELECT message FROM outbound_messages WHERE request_id=?',
                (row[0],),
            ).fetchone()
            connection.commit()
        finally:
            connection.close()
        return {
            'request_id': row[0],
            'cdr_id': row[1],
            'task_id': row[2],
            'purpose': row[3],
            'message': message_row[0] if message_row else '',
        }

    def record_inbound(
        self,
        *,
        caller: str,
        did: str,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        created = (now or datetime.now(UTC)).astimezone(UTC)
        request_id = f'in_{created.strftime("%Y%m%dT%H%M%S")}_{_hash(caller + did)[:12]}'
        cdr_id = (
            f'cdr_{created.strftime("%Y%m%dT%H%M%S")}_{_hash(request_id)[:12]}'
        )
        connection = self._connect()
        try:
            connection.execute(
                'INSERT OR IGNORE INTO calls(request_id,cdr_id,direction,to_e164,'
                'to_hash,cli,purpose,task_id,decision,reason,created_at)'
                ' VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (
                    request_id,
                    cdr_id,
                    'inbound',
                    did,
                    _hash(did),
                    caller,
                    'inbound',
                    '',
                    'allowed',
                    'inbound_answer',
                    created.isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return {'cdr_id': cdr_id, 'request_id': request_id}

    def record_outcome(
        self,
        cdr_id: str,
        *,
        outcome: str,
        duration_s: int = 0,
        recording_path: str = '',
        callback_requested: bool = False,
    ) -> dict[str, Any]:
        if outcome not in {
            'completed',
            'no_answer',
            'busy',
            'failed',
            'originate_failed',
            'congestion',
            'cancelled',
        }:
            raise VoiceBrokerDenied('invalid outcome')
        connection = self._connect()
        try:
            row = connection.execute(
                'UPDATE calls SET outcome=?,duration_s=?,recording_path=?,'
                'callback_requested=? WHERE cdr_id=?',
                (
                    outcome,
                    max(0, int(duration_s)),
                    recording_path[:500],
                    1 if callback_requested else 0,
                    cdr_id,
                ),
            )
            connection.commit()
        finally:
            connection.close()
        return {'status': 'recorded' if row.rowcount else 'unknown_cdr'}

    def doctor(self) -> dict[str, Any]:
        connection = self._connect()
        try:
            calls = connection.execute('SELECT COUNT(*) FROM calls').fetchone()
            pending = connection.execute(
                "SELECT COUNT(*) FROM calls WHERE outcome='pending'"
                " AND decision='allowed'",
            ).fetchone()
        finally:
            connection.close()
        stored = _canon_counts(self.canon_path)
        return {
            'status': 'ok',
            'db': str(self.db_path),
            'calls': int(calls[0]),
            'pending': int(pending[0]),
            'consents': stored['consents'],
            'blocklisted': stored['blocklisted'],
        }
