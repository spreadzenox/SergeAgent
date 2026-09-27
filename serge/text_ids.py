#!/usr/bin/env python3
"""Retirer des textes affichés à Julien les identifiants techniques."""

from __future__ import annotations

import re

ID_RE = re.compile(r'\b[twe]_[0-9a-f]{12}\b')


def strip_ids(text: str) -> str:
    """Retire les identifiants opaques (``t_…``, ``w_…``, ``e_…``).

    Exemple : « Ticket t_0a1b2c3d4e5f ouvert » devient « Ticket  ouvert ».
    """
    return ID_RE.sub('', text)
