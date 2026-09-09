#!/usr/bin/env python3
"""Signaux universels (B §4 couche 2) : 8 + OTHER. Enum fermée (P3)."""

from __future__ import annotations

from enum import StrEnum


class Signal(StrEnum):
    TECH_OK = 'TECH_OK'
    TECH_FAIL = 'TECH_FAIL'
    SEEN = 'SEEN'
    ENGAGED = 'ENGAGED'
    REPLIED = 'REPLIED'
    INTENT = 'INTENT'
    NEGATIVE = 'NEGATIVE'
    OPT_OUT = 'OPT_OUT'
    OTHER = 'OTHER'
