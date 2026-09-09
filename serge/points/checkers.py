#!/usr/bin/env python3
"""Checkers dét post-génération (P2/P3/P4...) : longueur, interdits, ton."""

from __future__ import annotations

from collections.abc import Sequence

AGGR_PATTERNS = (
    'derniere chance',
    'ultimatum',
    'sans reponse de ta part',
    'sans reponse de votre part',
    'je vais devoir',
    'tu ignores',
    'vous ignorez',
    'honte',
    'coupable',
    'menace',
    'huissier',
    'plainte',
)


def fold(text: str) -> str:
    """Normalise (casse, accents, apostrophes) pour les matchers.

    Args:
        text: Texte brut.

    Returns:
        Texte plié (comparaisons stables FR/EN).
    """
    folded = text.strip().lower()
    for src, dst in (
        ('é', 'e'),
        ('è', 'e'),
        ('ê', 'e'),
        ('à', 'a'),
        ('ç', 'c'),
        ('î', 'i'),
        ('ô', 'o'),
        ('û', 'u'),
        ('’', ''),
        ("'", ''),
    ):
        folded = folded.replace(src, dst)
    return folded


def check_length(text: str, max_chars: int) -> str:
    """Vérifie longueur (non vide, <= max).

    Returns:
        Code défaut ('' si OK).
    """
    if not text.strip():
        return 'vide'
    if len(text) > max_chars:
        return f'trop_long:{len(text)}'
    return ''


def check_forbidden(text: str, words: Sequence[str]) -> str:
    """Vérifie l'absence de mots interdits (insensible casse/accents).

    Returns:
        Le mot fautif ou ''.
    """
    folded = fold(text)
    for word in words:
        if word and fold(word) in folded:
            return word
    return ''


def check_aggressivity(text: str) -> str:
    """Détecteur dét d'agressivité (relances, voix).

    Returns:
        Le pattern fautif ou ''.
    """
    folded = fold(text)
    for pattern in AGGR_PATTERNS:
        if pattern in folded:
            return pattern
    return ''
