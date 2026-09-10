#!/usr/bin/env python3
"""MC projecteurs : socle (cache TTL, sig stables, enveloppes)."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from serge.mc import MC_VERSION
from serge.mc.proj_live import (
    project_feed,
    project_file,
    project_hero,
    project_jauges,
    project_urgents,
)

LIVE_TTL_S = 2.0
SLOW_TTL_S = 30.0
SLOW_SECTIONS = frozenset({'jauges'})


def canonical(payload: Any) -> str:
    """JSON canonique stable (trié, compact, ASCII).

    Args:
        payload: Objet sérialisable.

    Returns:
        Chaîne JSON déterministe (même objet = même chaîne).
    """
    return json.dumps(
        payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True
    )


def sig(payload: Any) -> str:
    """Signature stable d'un payload (16 hex).

    Args:
        payload: Objet sérialisable (JAMAIS de temps dedans).

    Returns:
        Préfixe SHA256 du JSON canonique.
    """
    return hashlib.sha256(canonical(payload).encode('utf-8')).hexdigest()[:16]


class SnapshotCache:
    """Cache TTL explicite par (page, section)."""

    def __init__(self, now_fn: Callable[[], float] | None = None) -> None:
        """Construit un cache vide (1 par connexion SSE).

        Args:
            now_fn: Horloge epoch (défaut : monotonic, injectable).
        """
        self._now = now_fn or time.monotonic
        self._slots: dict[tuple[str, str], tuple[Any, str, float]] = {}

    def get(
        self,
        page: str,
        section: str,
        ttl_s: float,
        compute: Callable[[], Any],
    ) -> tuple[Any, str, int]:
        """Payload + sig + âge (compute si absent/expiré).

        Args:
            page: Page MC (p0...).
            section: Section de la page.
            ttl_s: Durée de vie en secondes.
            compute: Fonction pure () -> payload.

        Returns:
            Tuple (payload, sig, age_ms).
        """
        now = self._now()
        slot = self._slots.get((page, section))
        if slot is not None:
            payload, digest, stored_at = slot
            if now - stored_at < ttl_s:
                return payload, digest, int((now - stored_at) * 1000)
        payload = compute()
        self._slots[(page, section)] = (payload, sig(payload), now)
        return payload, sig(payload), 0


def project_meta(conn: object, policy: object, now_iso: str) -> dict[str, Any]:
    """Section meta (version, statique — sig stable, T1/T2/A10).

    Args:
        conn: Connexion canon (ignorée, uniformité).
        policy: Policy (ignorée, uniformité).
        now_iso: Maintenant ISO (ignoré : JAMAIS de temps signé).

    Returns:
        Dict {mc_version}.
    """
    _ = (conn, policy, now_iso)
    return {'mc_version': MC_VERSION}


PROJECTORS: dict[str, Callable[..., dict[str, Any]]] = {
    'meta': project_meta,
    'hero': project_hero,
    'urgents': project_urgents,
    'file': project_file,
    'feed': project_feed,
    'jauges': project_jauges,
}

PAGE_SECTIONS: dict[str, list[str]] = {
    'p0': ['meta', 'hero', 'urgents', 'file', 'feed', 'jauges'],
}
