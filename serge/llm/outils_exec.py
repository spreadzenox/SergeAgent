#!/usr/bin/env python3
"""Registre d’outils pressables : schémas + handlers, sans boucle.

Ajouter un outil futur = une entrée dans SCHEMAS et HANDLERS.
La boucle (`boucle.py`) ne connaît pas les noms.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from serge.demande_capacite import CapaciteError, poser_demande
from serge.identite import IdentiteError, identite_serge
from serge.memory.search import memory_search
from serge.outils import SEED as TOOL_SEED

CODES_REFUS = frozenset({'inconnu', 'quota_couple', 'deja_fait', 'invalide'})

TOURS_MAX_ABSOLU = 12


@dataclass(frozen=True)
class ContexteOutil:
    """Contexte passé à chaque handler (canon + contrat du jugement)."""

    conn: sqlite3.Connection
    policy: Mapping[str, Any]
    spec: Mapping[str, Any]
    point_name: str


Handler = Callable[[ContexteOutil, dict[str, Any]], dict[str, Any]]


def _schema(
    name: str, description: str, properties: dict, required: list[str]
):
    return {
        'type': 'function',
        'function': {
            'name': name,
            'description': description,
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required,
            },
        },
    }


SCHEMAS: dict[str, dict[str, Any]] = {
    'memory_search': _schema(
        'memory_search',
        'Fouille la mémoire (leçons, épisodes, tickets). Lecture seule.',
        {
            'query': {'type': 'string', 'description': 'Question en français'},
            'types': {
                'type': 'array',
                'items': {'type': 'string'},
                'description': 'lesson, episode, ticket, artifact…',
            },
            'venture': {'type': 'string'},
            'since': {'type': 'string'},
            'tags': {'type': 'array', 'items': {'type': 'string'}},
            'top_k': {'type': 'integer'},
        },
        ['query'],
    ),
    'identity_basique': _schema(
        'identity_basique',
        'Identité publique de Serge (email, nom, SIRET). Pas l’IBAN.',
        {},
        [],
    ),
    'demande_capacite': _schema(
        'demande_capacite',
        'Demande une capacité manquante (ticket, pas d’invention).',
        {
            'besoin': {
                'type': 'string',
                'description': 'Ce qui manque (canal, outil, acte)',
            },
            'contexte': {
                'type': 'string',
                'description': 'Pourquoi, une phrase',
            },
        },
        ['besoin'],
    ),
}


def _exec_memory_search(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    query = str(args.get('query') or '').strip()
    if not query:
        return {'ok': False, 'code': 'invalide', 'detail': 'query vide'}
    context = ctx.spec.get('context')
    context = context if isinstance(context, dict) else {}
    couche = context.get('couche5')
    couche = couche if isinstance(couche, dict) else {}
    budget = couche.get('budget_tokens', 2000)
    if isinstance(budget, bool) or not isinstance(budget, int) or budget < 1:
        budget = 2000
    forbidden = context.get('forbidden')
    types = args.get('types')
    tags = args.get('tags')
    top_k = args.get('top_k', 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int):
        top_k = 5
    return memory_search(
        ctx.conn,
        query,
        point=ctx.point_name,
        types=types if isinstance(types, list) else None,
        venture=str(args.get('venture') or ''),
        since=str(args.get('since') or ''),
        tags=tags if isinstance(tags, list) else None,
        top_k=top_k,
        budget_tokens=budget,
        forbidden=forbidden if isinstance(forbidden, list) else None,
    )


def _exec_identity_basique(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    del ctx, args
    try:
        return identite_serge(volet='basique')
    except IdentiteError as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}


def _exec_demande_capacite(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    try:
        return poser_demande(
            ctx.conn,
            str(args.get('besoin') or ''),
            point=ctx.point_name,
            contexte=str(args.get('contexte') or ''),
        )
    except CapaciteError as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}


HANDLERS: dict[str, Handler] = {
    'memory_search': _exec_memory_search,
    'identity_basique': _exec_identity_basique,
    'demande_capacite': _exec_demande_capacite,
}


def tours_max(policy: Mapping[str, Any]) -> int:
    """Plafond global de tours d’outils (12, raboté par la policy).

    Args:
        policy: Policy (``quotas.llm_outil_tours_max``).

    Returns:
        Entier 0–12.
    """
    quotas = policy.get('quotas')
    raw = (quotas or {}).get('llm_outil_tours_max', TOURS_MAX_ABSOLU)
    if isinstance(raw, bool) or not isinstance(raw, int):
        return TOURS_MAX_ABSOLU
    return max(0, min(TOURS_MAX_ABSOLU, raw))


def outils_pressables(spec: Mapping[str, Any]) -> tuple[str, ...]:
    """Outils offerts à ce jugement : handler + contrat (couche 5 / yaml).

    Args:
        spec: Déclaration du point (registre).

    Returns:
        Ids stables : couche 5, puis yaml, puis outils partout.
    """
    context = spec.get('context')
    context = context if isinstance(context, dict) else {}
    couche = context.get('couche5')
    couche = couche if isinstance(couche, dict) else {}
    ids: list[str] = []
    if couche.get('allowed') is True and 'memory_search' in HANDLERS:
        ids.append('memory_search')
    extra = context.get('tools')
    if isinstance(extra, list):
        for raw in extra:
            ident = str(raw or '')
            if ident == 'memory_search':
                continue
            if ident in HANDLERS and ident not in ids:
                ids.append(ident)
    for row in TOOL_SEED:
        ident = row[0]
        partout = row[7]
        if partout != 1 or ident == 'memory_search':
            continue
        if ident in HANDLERS and ident not in ids:
            ids.append(ident)
    return tuple(ids)


def schemas_openai(ids: tuple[str, ...]) -> list[dict[str, Any]]:
    """Schémas OpenAI des ids pressables (ignore un id sans schéma).

    Args:
        ids: Outils à exposer.

    Returns:
        Liste de blocs ``type=function``.
    """
    return [SCHEMAS[ident] for ident in ids if ident in SCHEMAS]


CLE_QUOTAS = 'serge_outil_quotas'


def restants_par_outil(
    pressables: tuple[str, ...],
    *,
    spent: Mapping[str, int],
    spec: Mapping[str, Any],
    policy: Mapping[str, Any],
    tours_faits: int,
    tours_plafond: int,
) -> dict[str, int]:
    """Appels encore possibles par outil (min couple / tours globaux).

    Args:
        pressables: Outils offerts à ce jugement.
        spent: Appels déjà réussis dans cette boucle.
        spec: Déclaration du point.
        policy: Policy (plafonds).
        tours_faits: Tours d’outils déjà joués.
        tours_plafond: Cap global (≤ 12).

    Returns:
        Mapping outil → entier ≥ 0. Illimité côté couple = tours restants.
    """
    tours_restants = max(0, tours_plafond - tours_faits)
    out: dict[str, int] = {}
    for tool_id in pressables:
        couple = quota_couple(spec, tool_id, policy)
        if couple is None:
            out[tool_id] = tours_restants
        else:
            out[tool_id] = max(
                0, min(couple - spent.get(tool_id, 0), tours_restants)
            )
    return out


def payload_quotas(
    restants: Mapping[str, int], tours_restants: int
) -> dict[str, Any]:
    """Faits de quota à injecter (JSON, P3 — pas de prose).

    Args:
        restants: Appels encore possibles par outil.
        tours_restants: Tours d’outils encore possibles.

    Returns:
        Dict marqué ``serge_outil_quotas``.
    """
    return {
        CLE_QUOTAS: True,
        'tours_restants': tours_restants,
        'appels_restants': dict(restants),
    }


def quota_couple(
    spec: Mapping[str, Any], tool_id: str, policy: Mapping[str, Any]
) -> int | None:
    """Plafond optionnel pour ce couple (outil × jugement). None = illimité.

    Args:
        spec: Déclaration du point.
        tool_id: Outil demandé.
        policy: Policy (repli ``memory_search``).

    Returns:
        Plafond ≥ 0, ou ``None`` si seul le cap global s’applique.
    """
    context = spec.get('context')
    context = context if isinstance(context, dict) else {}
    raw = context.get('tool_quotas')
    if isinstance(raw, dict) and tool_id in raw:
        value = raw[tool_id]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            return 0
        return value
    if tool_id == 'memory_search':
        couche = context.get('couche5')
        couche = couche if isinstance(couche, dict) else {}
        max_calls = couche.get('max_calls')
        if isinstance(max_calls, int) and not isinstance(max_calls, bool):
            return max(0, max_calls)
        quotas = policy.get('quotas') if isinstance(policy, Mapping) else {}
        fallback = (quotas or {}).get('memory_search_per_cycle_per_point')
        if isinstance(fallback, int) and not isinstance(fallback, bool):
            return max(0, fallback)
    if tool_id == 'demande_capacite':
        return 1
    return None


def peut_appeler(
    tool_id: str,
    *,
    pressables: tuple[str, ...],
    spent: Mapping[str, int],
    spec: Mapping[str, Any],
    policy: Mapping[str, Any],
    deja: set[tuple[str, str]],
    arguments: str,
) -> str | None:
    """None si l’appel passe, sinon un code de ``CODES_REFUS``.

    Args:
        tool_id: Outil demandé.
        pressables: Outils offerts à ce jugement.
        spent: Appels déjà réussis.
        spec: Déclaration du point.
        policy: Policy.
        deja: Couples (outil, arguments) déjà exécutés.
        arguments: Arguments normalisés.

    Returns:
        Code de refus, ou ``None``.
    """
    if tool_id not in HANDLERS or tool_id not in pressables:
        return 'inconnu'
    if (tool_id, arguments) in deja:
        return 'deja_fait'
    cap = quota_couple(spec, tool_id, policy)
    if cap is not None and spent.get(tool_id, 0) >= cap:
        return 'quota_couple'
    return None
