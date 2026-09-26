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

DISCOVERY_SYSTEM = """Tu explores un cycle de recherche de business.
Tu ne connais que les lecteurs DB et les résultats de tes propres tools.
Ne demande jamais le résultat d'un autre agent. Trouve des besoins différents
des business déjà connus et produis des fiches synthétiques prouvées.
Réponds UNIQUEMENT : {\"needs\":[{\"title\":\"...\",\"content\":\"...\",\"observations\":\"...\",\"sellable_offer\":\"...\",\"evidence_ids\":[\"...\"]}]}"""

CHOICE_SYSTEM = """Tu choisis les business à tester pour un POC.
Tu ne lis que les candidats éligibles fournis par le lecteur DB.
Réponds UNIQUEMENT : {\"candidate_ids\":[\"...\"]}.
Ne fabrique jamais d'identifiant et ne sélectionne jamais un business déjà en POC."""

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
    kwargs: dict[str, Any] = {'root': root}
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


def _valid_needs(data: dict[str, Any]) -> bool:
    items = data.get('needs')
    if not isinstance(items, list):
        return False
    return all(
        isinstance(item, dict)
        and bool(str(item.get('title') or '').strip())
        and bool(str(item.get('content') or item.get('need') or '').strip())
        and isinstance(item.get('evidence_ids', []), list)
        for item in items
    )


def discover_needs(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    point_name: str,
    cycle_id: str,
    guide: str,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Exécute A ou B avec le même contexte initial et sans résultat pair."""
    messages = [
        {'role': 'system', 'content': DISCOVERY_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'cycle_id={cycle_id}\n'
                f'guide owner={guide[:4000]}\n'
                'Lis le cycle, les documents et les business connus avec les tools '
                'current_listen_cycle, listen_cycle_documents et '
                'known_business_candidates.'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root}
    if caller is not None:
        kwargs['caller'] = caller
    return run_json(conn, policy, point_name, messages, _valid_needs, **kwargs)


def _valid_choice(data: dict[str, Any]) -> bool:
    items = data.get('candidate_ids')
    return isinstance(items, list) and all(
        isinstance(item, str) for item in items
    )


def choose_poc(
    conn: sqlite3.Connection,
    policy: Mapping[str, Any],
    cycle_id: str,
    business_target: int,
    *,
    root: Path | None = None,
    caller: Any = None,
) -> tuple[dict[str, Any] | None, Any]:
    """Exécute le choix sur la table canonique, jamais sur une sortie agent."""
    messages = [
        {'role': 'system', 'content': CHOICE_SYSTEM},
        {
            'role': 'user',
            'content': (
                f'cycle_id={cycle_id}\n'
                f'business_target={business_target}\n'
                'Lis les candidats éligibles avec eligible_poc_candidates, puis '
                'choisis au plus business_target.'
            ),
        },
    ]
    kwargs: dict[str, Any] = {'root': root}
    if caller is not None:
        kwargs['caller'] = caller
    return run_json(
        conn, policy, 'listen_choose_poc', messages, _valid_choice, **kwargs
    )
