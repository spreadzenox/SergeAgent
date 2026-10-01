#!/usr/bin/env python3
"""Appeler un modèle : le client, le modèle par niveau, la clé, le budget."""

from __future__ import annotations

from serge.llm.client import ChatResult, LlmError, chat
from serge.llm.runtime import (
    budget_reached,
    daily_tokens,
    read_api_key,
    resolve_model,
)

__all__ = [
    'ChatResult',
    'LlmError',
    'budget_reached',
    'chat',
    'daily_tokens',
    'read_api_key',
    'resolve_model',
]
