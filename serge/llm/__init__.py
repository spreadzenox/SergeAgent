#!/usr/bin/env python3
"""Couche LLM (C §0) : client metered + runtime (kill-switch, budget)."""

from __future__ import annotations

from serge.llm.client import ChatResult, LlmError, chat
from serge.llm.runtime import (
    RunResult,
    daily_tokens,
    read_api_key,
    resolve_model,
    run_point,
    run_registered_point,
)

__all__ = [
    'ChatResult',
    'LlmError',
    'RunResult',
    'chat',
    'daily_tokens',
    'read_api_key',
    'resolve_model',
    'run_point',
    'run_registered_point',
]
