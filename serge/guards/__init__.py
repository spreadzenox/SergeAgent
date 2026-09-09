#!/usr/bin/env python3
"""Guards: fail-closed, déterministes. 0 LLM, jamais d'exception métier."""

from __future__ import annotations

from serge.guards.check import check
from serge.guards.reasons import Reason, Verdict

__all__ = ['Reason', 'Verdict', 'check']
