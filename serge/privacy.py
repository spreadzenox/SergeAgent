#!/usr/bin/env python3
"""Empreintes PII uniques (P4 : consent/blocklist voix + guards)."""

from __future__ import annotations

import hashlib


def subject_hash(subject: str) -> str:
    """Empreinte stable d'un sujet (email, E.164) pour le canon.

    Normalise (casse, espaces) avant hachage : le broker voix et les
    guards partagent les mêmes lignes consent/blocklist.

    Args:
        subject: Email ou numéro (brut).

    Returns:
        Hex sha256 du sujet normalisé.
    """
    clean = subject.strip().lower()
    return hashlib.sha256(clean.encode('utf-8')).hexdigest()
