#!/usr/bin/env python3
"""Écoute J (J0) : collecte DET (RSS/API), respect rate-limits, dédup."""

from __future__ import annotations

from serge.listen.collectors import ListenError, fetch_rss, parse_rss

__all__ = ['ListenError', 'fetch_rss', 'parse_rss']
