#!/usr/bin/env python3
"""MC SSE : framing signé + boucle d'envoi par connexion."""

from __future__ import annotations

import json
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from serge.db.store import open_db, utcnow
from serge.mc.projectors import (
    LIVE_TTL_S,
    PROJECTORS,
    SLOW_SECTIONS,
    SLOW_TTL_S,
    SnapshotCache,
    sig,
)
from serge.policy_snapshots import policy_en_vigueur


def format_event(
    section: str, digest: str, age_ms: int, payload: Any
) -> bytes:
    """Formate un event SSE (nom + sig + âge + payload, JSON 1 ligne).

    Args:
        section: Nom de la section (routage client).
        digest: Signature du payload.
        age_ms: Âge du snapshot (hors signature).
        payload: Données (sans temps).

    Returns:
        Octets `event: section\\ndata: {...}\\n\\n`.
    """
    body = json.dumps(
        {
            'section': section,
            'sig': digest,
            'age_ms': age_ms,
            'payload': payload,
        },
        ensure_ascii=False,
    )
    return f'event: section\ndata: {body}\n\n'.encode()


def stream_page(
    wfile: Any,
    db_path: Path,
    policy: dict[str, Any],
    page: str,
    sections: list[str],
    cache: SnapshotCache,
    tick_s: float = 2.0,
    max_ticks: int | None = None,
) -> int:
    """Boucle SSE (bloquant, 1 thread/connexion, DB rouverte par tick).

    Args:
        wfile: Flux d'écriture (flush après chaque tick).
        db_path: Canon (rouvert à chaque tick : vue fraîche).
        policy: Ignoré — la policy vient du dernier snapshot.
        page: Page MC (clé de cache).
        sections: Sections à envoyer (ordre stable).
        cache: Cache TTL de la connexion.
        tick_s: Intervalle entre ticks.
        max_ticks: Arrêt après N ticks (tests uniquement).

    Returns:
        Nombre de ticks envoyés.

    Raises:
        BrokenPipeError: Client parti (normal).
        ConnectionResetError: Client parti (normal).
    """
    _ = policy
    ticks = 0
    while True:
        with closing(open_db(db_path)) as conn:
            live = policy_en_vigueur(conn)
            for section in sections:
                projector = PROJECTORS[section]
                ttl = SLOW_TTL_S if section in SLOW_SECTIONS else LIVE_TTL_S
                payload, digest, age = cache.get(
                    page,
                    section,
                    ttl,
                    lambda p=projector, pol=live: p(conn, pol, utcnow()),
                )
                wfile.write(format_event(section, digest, age, payload))
        wfile.flush()
        ticks += 1
        if max_ticks is not None and ticks >= max_ticks:
            return ticks
        time.sleep(tick_s)


def state_payload(
    db_path: Path,
    policy: dict[str, Any],
    page: str,
    sections: list[str],
) -> dict[str, Any]:
    """Payload 1-shot (fetch initial, QA — mêmes projecteurs que le SSE).

    Args:
        db_path: Canon.
        policy: Ignoré — la policy vient du dernier snapshot.
        page: Page MC.
        sections: Sections à projeter.

    Returns:
        Dict {page, sections: {nom: {sig, age_ms: 0, payload}}}.
    """
    _ = policy
    out: dict[str, Any] = {'page': page, 'sections': {}}
    with closing(open_db(db_path)) as conn:
        live = policy_en_vigueur(conn)
        for section in sections:
            payload = PROJECTORS[section](conn, live, utcnow())
            out['sections'][section] = {
                'sig': sig(payload),
                'age_ms': 0,
                'payload': payload,
            }
    return out
