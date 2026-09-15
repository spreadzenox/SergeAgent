#!/usr/bin/env python3
"""Champs d’identité optionnels (prénom, IBAN…) : pas le gate de boot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

CLES = (
    'prenom',
    'nom',
    'pseudo',
    'siret',
    'iban',
    'adresse_facturation',
)


def extraire(identity: Mapping[str, Any]) -> dict[str, str]:
    """Lit les champs optionnels (vides si absents)."""
    return {cle: str(identity.get(cle) or '').strip() for cle in CLES}


def lignes_toml(
    ident: Mapping[str, Any], quote: Callable[[str], str]
) -> list[str]:
    """Lignes TOML des champs optionnels."""
    return [f'{cle} = {quote(str(ident.get(cle) or ""))}' for cle in CLES]
