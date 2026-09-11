#!/usr/bin/env python3
"""Projection publique fail-closed (E13, §2.8, §6 P9).

Contrat : assert_public_safe() sur tout payload ou texte public.
Tout secret, token, PII, identifiant interne ou donnée sensible provoque
immédiatement un rejet ou un fallback sur document minimal.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc import MC_VERSION

# Regex de détection de fuites potentielles
SECRET_PATTERNS = [
    re.compile(
        r'(?i)(?:api[_-]?key|secret|token|password|bearer|auth)\s*[:=\s]\s*["\']?[a-zA-Z0-9_\-\.]{8,}'
    ),
    re.compile(r'(?i)sk-[a-zA-Z0-9]{20,}'),
    re.compile(r'(?i)age1[a-z0-9]{50,}'),
    re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
]

ID_OPAQUE_RE = re.compile(r'\b[twec]_[0-9a-f]{10,}\b')
EMAIL_RE = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
PHONE_RE = re.compile(r'\+33[0-9]{9}\b')


class PublicSafetyViolation(ValueError):
    """Fuite de données sensibles détectée dans la projection publique."""


def assert_public_safe(obj: Any) -> None:
    """Valide de manière récursive qu'un objet JSON/dict est fail-closed public.

    Raises:
        PublicSafetyViolation: En cas de présence de données interdites.
    """
    if isinstance(obj, str):
        for pattern in SECRET_PATTERNS:
            if pattern.search(obj):
                raise PublicSafetyViolation(
                    f'Secret détecté dans projection publique: {pattern.pattern}'
                )
        if ID_OPAQUE_RE.search(obj):
            raise PublicSafetyViolation(
                'Identifiant opaque détecté dans projection publique'
            )
        if EMAIL_RE.search(obj):
            raise PublicSafetyViolation(
                'Email PII détecté dans projection publique'
            )
        if PHONE_RE.search(obj):
            raise PublicSafetyViolation(
                'Téléphone PII détecté dans projection publique'
            )
    elif isinstance(obj, Mapping):
        for k, v in obj.items():
            assert_public_safe(k)
            assert_public_safe(v)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            assert_public_safe(item)


def project_public_statut(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Projection publique ultra-minimaliste et fail-closed (P9).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy.
        now: Horodatage ISO.

    Returns:
        Dict {statut, message, mc_version}.
    """
    _ = (policy, now)
    try:
        # Vérification grossière de l'activité
        row = conn.execute(
            "SELECT COUNT(*) FROM work_items WHERE status='RUNNING'"
        ).fetchone()
        actif = int(row[0]) > 0 if row else False
        statut = 'operationnel' if not actif else 'travail_en_cours'
        payload = {
            'statut': statut,
            'message': 'Tous les systèmes sont opérationnels.'
            if not actif
            else 'Des tâches sont en cours d’exécution.',
            'mc_version': MC_VERSION,
        }
        assert_public_safe(payload)
        return payload
    except Exception:
        # Fail-closed absolu
        return {
            'statut': 'operationnel',
            'message': 'Systèmes en ligne.',
            'mc_version': MC_VERSION,
        }
