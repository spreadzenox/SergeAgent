#!/usr/bin/env python3
"""Lecture secrets instance (P4 : un seul lecteur, voix + LLM + rails)."""

from __future__ import annotations

import re
from pathlib import Path


def read_secret_file(path: Path) -> str:
    """Lit un secret (token brut ou dotenv KEY=value, 1re ligne).

    Args:
        path: Fichier secret (absent/illisible = chaîne vide).

    Returns:
        Le secret déshabillé (jamais logué par les appelants).
    """
    try:
        text = path.read_text(encoding='utf-8').strip()
    except OSError:
        return ''
    if not text:
        return ''
    first = text.splitlines()[0].strip()
    match = re.match(r'^([A-Za-z_][A-Za-z0-9_]*)=(.*)$', first)
    if match:
        key, rest = match.group(1), match.group(2)
        if rest.strip():
            return rest.strip().strip('"').strip("'")
        if re.fullmatch(r'[A-Z_][A-Z0-9_]*', key):
            return ''
    return first
