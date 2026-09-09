#!/usr/bin/env python3
"""Verdicts guards: enum fermé (P3), codes routables, jamais de prose."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Reason(StrEnum):
    OK = 'OK'
    DUPLICATE_IDEMPOTENT = 'DUPLICATE_IDEMPOTENT'
    BLOCKLISTED = 'BLOCKLISTED'
    NO_CONSENT = 'NO_CONSENT'
    QUOTA_CONTACT_30D = 'QUOTA_CONTACT_30D'
    OUTSIDE_WINDOW = 'OUTSIDE_WINDOW'
    UNKNOWN_CHANNEL = 'UNKNOWN_CHANNEL'


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: Reason
    retry_at: str = ''
    duplicate: bool = False
