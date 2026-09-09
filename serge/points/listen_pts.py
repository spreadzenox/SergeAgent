#!/usr/bin/env python3
"""Point J1 : cluster_demand (HYB + LLM-1, T2). Labels + scores clusters.

Embeddings/clustering = outil dét (appelant) ; labeling/scoring = LLM-1.
Rubric : volume/intensité/récurrence/willingness 0-1 + opportunité chaude.
Repli : clusters bruts sans labels.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from serge.points.jsonio import run_json

CLUSTER_SYSTEM = """Tu qualifies des clusters de demande (français/anglais) issus d'écoute (forums, avis, réseaux).
Rubric 0-1 : volume (combien), intensite (douleur/émotion), recurrence (répétition dans le temps), willingness (prêt à payer).
Réponds UNIQUEMENT un objet JSON : {"clusters": [{"id": "...", "label": "...", "volume": 0.0-1.0, "intensite": 0.0-1.0, "recurrence": 0.0-1.0, "willingness": 0.0-1.0, "opportunite_chaude": true|false}]}.
opportunite_chaude = volume ET willingness élevés. Verbatims anonymisés, ne les recopie pas."""


def _valid_clusters(data: dict[str, Any], ids: set[str]) -> bool:
    items = data.get('clusters')
    if not isinstance(items, list) or not items:
        return False
    for item in items:
        if not isinstance(item, dict):
            return False
        if item.get('id') not in ids:
            return False
        if not item.get('label'):
            return False
        for key in ('volume', 'intensite', 'recurrence', 'willingness'):
            try:
                value = float(item.get(key, -1))
            except (TypeError, ValueError):
                return False
            if not 0.0 <= value <= 1.0:
                return False
        if not isinstance(item.get('opportunite_chaude'), bool):
            return False
    return True


def label_clusters(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    clusters: Sequence[Mapping[str, Any]],
    *,
    root: Path | None = None,
    caller: Any = None,
) -> dict[str, Any]:
    """J1 : labels + scores de clusters bruts (batch hebdo).

    Args:
        conn: Connexion canon (commit par l'appelant).
        policy: Policy (contrat uniforme).
        clusters: [{id, verbatims[échantillonnés]}] (appelant dét).
        root: config_root (défaut : instance).
        caller: Appel LLM (défaut : client réel).

    Returns:
        Dict clusters/fallback (repli = bruts sans labels).
    """
    ids = {str(item.get('id')) for item in clusters}
    blocks = []
    for item in clusters:
        samples = '\n'.join(
            f'  - {str(line)[:200]}'
            for line in (item.get('verbatims') or [])[:8]
        )
        blocks.append(f'Cluster {item.get("id")} :\n{samples}')
    messages = [
        {'role': 'system', 'content': CLUSTER_SYSTEM},
        {'role': 'user', 'content': '\n\n'.join(blocks)[:3000]},
    ]
    kwargs: dict[str, Any] = {'root': root, 'max_tokens': 1000}
    if caller is not None:
        kwargs['caller'] = caller
    data, result = run_json(
        conn,
        policy,
        'cluster_demand',
        messages,
        lambda obj: _valid_clusters(obj, ids),
        **kwargs,
    )
    if data is None:
        reason = result.fallback if result is not None else 'error'
        return {
            'clusters': [
                {
                    'id': str(item.get('id')),
                    'label': '',
                    'volume': 0.0,
                    'intensite': 0.0,
                    'recurrence': 0.0,
                    'willingness': 0.0,
                    'opportunite_chaude': False,
                }
                for item in clusters
            ],
            'fallback': reason or 'parse',
        }
    return {
        'clusters': [
            {
                'id': str(item['id']),
                'label': str(item['label']),
                'volume': float(item['volume']),
                'intensite': float(item['intensite']),
                'recurrence': float(item['recurrence']),
                'willingness': float(item['willingness']),
                'opportunite_chaude': bool(item['opportunite_chaude']),
            }
            for item in data['clusters']
        ],
        'fallback': '',
    }
