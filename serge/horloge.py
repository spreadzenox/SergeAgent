#!/usr/bin/env python3
"""Horloge canon : un seul format UTC ISO."""

from __future__ import annotations

from datetime import UTC, datetime


def iso_utc() -> str:
    """UTC ISO-8601 (même format partout)."""
    return datetime.now(UTC).isoformat()
