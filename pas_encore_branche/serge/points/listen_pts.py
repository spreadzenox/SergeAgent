#!/usr/bin/env python3
"""Invocations de l'étape 1 : découvrir des besoins (A et B), choisir un POC.

Les deux découvertes reçoivent le même contexte et ne voient jamais la
sortie de l'autre. Le choix lit seulement les candidats éligibles.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
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
