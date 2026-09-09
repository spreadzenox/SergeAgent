#!/usr/bin/env python3
"""Mémoire (D-spec) : leçons, résumés, recherche, consolidation, oubli."""

from __future__ import annotations

from serge.memory.lessons import (
    add_lesson,
    add_pitfall,
    add_playbook,
    confirm_lesson,
    expire_lessons,
    infirm_lesson,
    set_lesson_status,
    top_lessons,
)
from serge.memory.search import (
    ensure_index,
    index_document,
    memory_search,
    rebuild_index,
    redact_text,
    searches_spent,
)
from serge.memory.summaries import (
    get_summary,
    put_summary,
    rollback_summary,
    serge_md_text,
)

__all__ = [
    'add_lesson',
    'add_pitfall',
    'add_playbook',
    'confirm_lesson',
    'ensure_index',
    'expire_lessons',
    'get_summary',
    'index_document',
    'infirm_lesson',
    'memory_search',
    'put_summary',
    'rebuild_index',
    'redact_text',
    'rollback_summary',
    'searches_spent',
    'serge_md_text',
    'set_lesson_status',
    'top_lessons',
]
