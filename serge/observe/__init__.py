#!/usr/bin/env python3
"""Observation (B §4) : normaliseurs natif→signal + routeur universel."""

from __future__ import annotations

from serge.observe.normalize import normalize
from serge.observe.router import ingest
from serge.observe.signals import Signal

__all__ = ['Signal', 'ingest', 'normalize']
