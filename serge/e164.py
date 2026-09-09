#!/usr/bin/env python3
"""Validation E.164 unique (P4 : un seul endroit, kit + runtime)."""

from __future__ import annotations

import re

E164_RE = re.compile(r'^\+[1-9][0-9]{6,14}$')


def normalize(raw: str) -> str:
    """Normalise un numéro saisi (espaces, points, tirets) avant validation.

    Args:
        raw: Numéro brut (ex. '+336 95.17-04-42').

    Returns:
        Numéro nettoyé (ex. '+33695170442'). Ne rajoute jamais de '+'.
    """
    return (
        str(raw or '')
        .strip()
        .replace(' ', '')
        .replace('.', '')
        .replace('-', '')
    )


def is_valid(raw: str) -> bool:
    """True si le numéro est un E.164 valide après normalisation.

    Args:
        raw: Numéro brut.

    Returns:
        True si `+` suivi de 7 à 15 chiffres (1er non nul).
    """
    return bool(E164_RE.match(normalize(raw)))
