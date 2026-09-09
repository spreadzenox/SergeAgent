#!/usr/bin/env python3
"""Chemins d'instance uniques (P4 : system_root, config_root)."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any


def system_root() -> Path:
    """Racine système de l'instance (SERGE_SYSTEM_ROOT).

    Returns:
        system_root effectif (défaut : instance julien-vps).
    """
    return Path(
        os.environ.get('SERGE_SYSTEM_ROOT', '/home/serge/serge-system')
    )


def config_root(data: dict[str, Any] | None = None) -> Path:
    """Racine config lue depuis le TOML d'instance (paths.config_root).

    Args:
        data: TOML déjà chargé (None = relu depuis SERGE_INSTANCE_FILE).

    Returns:
        config_root effectif (défaut : ~/.config/serge).
    """
    if data is None:
        raw = os.environ.get('SERGE_INSTANCE_FILE', '').strip()
        if raw:
            try:
                data = tomllib.loads(Path(raw).read_text(encoding='utf-8'))
            except (OSError, tomllib.TOMLDecodeError):
                data = None
    paths = (data or {}).get('paths') or {}
    home = Path(str(paths.get('home') or os.path.expanduser('~')))
    override = str(paths.get('config_root') or '')
    return Path(override) if override else home / '.config/serge'
