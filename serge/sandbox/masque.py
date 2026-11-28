#!/usr/bin/env python3
"""Masquer un secret dans un texte qu'un modèle va lire : une page, la
sortie d'une commande du chantier."""

from __future__ import annotations

import re


def masquer(texte: str, secrets: set[str]) -> str:
    """Remplace chaque secret par ``••••``, même remis en forme par la
    page : ``4242 4242 4242 4242`` ou ``12 / 34``."""
    for secret in secrets:
        motif = r'[\s/.\-]*'.join(
            re.escape(c) for c in secret if not c.isspace()
        )
        if motif:
            texte = re.sub(motif, '••••', texte)
    return texte
