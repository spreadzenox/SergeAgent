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

from serge.funnels.contacts import ContactError, upsert_contact_references
from serge.identite import IdentiteError, identite_serge
from serge.listen.web import search_public
from serge.memory.search import memory_search

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
    'web_search': _schema(
        'web_search',
        'Cherche sur le web public, en lecture seule.',
        {
            'query': {'type': 'string'},
            'limit': {'type': 'integer'},
        },
        ['query'],
    ),
    'identity_basique': _schema(
        'identity_basique',
        'Identité publique de Serge (email, nom, SIRET). Pas l’IBAN.',
        {},
        [],
    ),
    'contact_upsert': _schema(
        'contact_upsert',
        'Crée ou enrichit un contact avec des références JSON par canal. '
        'La déduplication est faite dans toute la venture avant toute création.',
        {
            'venture_id': {
                'type': 'string',
                'description': 'Identifiant de la venture dans le contexte courant',
            },
            'display': {
                'type': 'string',
                'description': 'Nom affiché du contact, sans secret',
            },
            'contact_reference_by_canal': {
                'type': 'object',
                'description': (
                    'Map canal -> référence. Email: address; voice: phone; '
                    'autres canaux: handle ou profile_url.'
                ),
                'additionalProperties': {
                    'type': 'object',
                    'properties': {
                        'active': {'type': 'boolean'},
                        'address': {'type': 'string'},
                        'phone': {'type': 'string'},
                        'handle': {'type': 'string'},
                        'profile_url': {'type': 'string'},
                    },
                    'additionalProperties': False,
                },
            },
            'reference': {
                'type': 'object',
                'description': (
                    'Référence unique structurée, par exemple '
                    "{'channel':'email','address':'...'}"
                ),
                'properties': {
                    'channel': {'type': 'string'},
                    'canal': {'type': 'string'},
                    'active': {'type': 'boolean'},
                    'address': {'type': 'string'},
                    'phone': {'type': 'string'},
                    'handle': {'type': 'string'},
                    'profile_url': {'type': 'string'},
                },
                'additionalProperties': False,
            },
        },
        ['venture_id', 'display'],
    ),
}
SCHEMAS['contact_upsert']['function']['parameters'].update(
    {
        'additionalProperties': False,
        'anyOf': [
            {'required': ['contact_reference_by_canal']},
            {'required': ['reference']},
        ],
    }
)


def _exec_memory_search(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    query = str(args.get('query') or '').strip()
    if not query:
        return {'ok': False, 'code': 'invalide', 'detail': 'query vide'}
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
    )


def _exec_identity_basique(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    del ctx, args
    try:
        return identite_serge(volet='basique')
    except IdentiteError as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}


def _exec_contact_upsert(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    """Upsert contact borné aux références JSON canoniques."""
    forbidden = {'email', 'phone', 'venue', 'handle', 'profile_url'}
    if forbidden.intersection(args):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'les anciennes colonnes de contact sont interdites',
        }
    context = ctx.spec.get('context')
    context = context if isinstance(context, Mapping) else {}
    venture_id = str(
        args.get('venture_id') or context.get('venture_id') or ''
    ).strip()
    display = str(args.get('display') or '').strip()
    if not venture_id or not display:
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'venture_id et display requis',
        }
    if (
        ctx.conn.execute(
            'SELECT 1 FROM ventures WHERE id=?', (venture_id,)
        ).fetchone()
        is None
    ):
        return {'ok': False, 'code': 'invalide', 'detail': 'venture inconnue'}

    reference_map = args.get('contact_reference_by_canal')
    single_reference = args.get('reference')
    if reference_map is not None and single_reference is not None:
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'une seule forme de référence est acceptée',
        }
    raw_references = (
        reference_map if reference_map is not None else single_reference
    )
    if not isinstance(raw_references, Mapping):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'référence JSON requise',
        }
    try:
        references = raw_references
        is_single = bool(
            single_reference is not None
            or references.get('channel')
            or references.get('canal')
        )
        candidates = [references] if is_single else list(references.values())
        for reference in candidates:
            if not isinstance(reference, Mapping):
                continue
            if 'venue' in reference:
                return {
                    'ok': False,
                    'code': 'invalide',
                    'detail': 'le champ legacy venue est interdit',
                }
            if not isinstance(reference.get('active', True), bool):
                return {
                    'ok': False,
                    'code': 'invalide',
                    'detail': 'active doit être booléen',
                }
        return upsert_contact_references(
            ctx.conn, venture_id, display, references
        )
    except (ContactError, TypeError, ValueError) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}


def _exec_db_read_tool(
    ctx: ContexteOutil, tool_id: str, args: dict[str, Any]
) -> dict[str, Any]:
    from serge.db.query_builder import execute_db_read

    try:
        return execute_db_read(ctx.conn, tool_id, args)
    except (ValueError, sqlite3.Error) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}


def _exec_web_search(
    ctx: ContexteOutil, args: dict[str, Any]
) -> dict[str, Any]:
    del ctx
    query = str(args.get('query') or '')
    limit = args.get('limit', 5)
    if isinstance(limit, bool) or not isinstance(limit, int):
        limit = 5
    return search_public(query, limit)


HANDLERS: dict[str, Handler] = {
    'memory_search': _exec_memory_search,
    'identity_basique': _exec_identity_basique,
    'contact_upsert': _exec_contact_upsert,
    'web_search': _exec_web_search,
}


def _db_tool_ids(conn: sqlite3.Connection | None) -> set[str]:
    if conn is None:
        return set()
    from serge.db.query_builder import db_read_tool_ids

    return set(db_read_tool_ids(conn))


def _handler_exists(conn: sqlite3.Connection | None, tool_id: str) -> bool:
    return tool_id in HANDLERS or tool_id in _db_tool_ids(conn)


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


def outils_pressables(
    spec: Mapping[str, Any], conn: sqlite3.Connection | None = None
) -> tuple[str, ...]:
    """Outils offerts à ce jugement : handlers et jonction DB.

    Args:
        spec: Déclaration du point (registre).

    Returns:
        Ids stables des tools DB affectés au point.
    """
    declared_db_tools = spec.get('db_tools')
    db_filter = (
        set(declared_db_tools)
        if isinstance(declared_db_tools, (list, tuple))
        else None
    )
    ids: list[str] = []
    if isinstance(declared_db_tools, (list, tuple)):
        for raw in declared_db_tools:
            ident = str(raw or '')
            if (
                _handler_exists(conn, ident)
                and ident not in ids
                and (db_filter is None or ident in db_filter)
            ):
                ids.append(ident)
    return tuple(ids)


def schemas_openai(
    ids: tuple[str, ...], conn: sqlite3.Connection | None = None
) -> list[dict[str, Any]]:
    """Schémas OpenAI des ids pressables (ignore un id sans schéma).

    Args:
        ids: Outils à exposer.

    Returns:
        Liste de blocs ``type=function``.
    """
    from serge.db.query_builder import openai_schema_for_tool

    out: list[dict[str, Any]] = []
    for ident in ids:
        if ident in SCHEMAS:
            out.append(SCHEMAS[ident])
        elif conn is not None and ident in _db_tool_ids(conn):
            out.append(openai_schema_for_tool(conn, ident))
    return out


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
        quotas = policy.get('quotas') if isinstance(policy, Mapping) else {}
        fallback = (quotas or {}).get('memory_search_per_cycle_per_point')
        if isinstance(fallback, int) and not isinstance(fallback, bool):
            return max(0, fallback)
    return None


def peut_appeler(
    tool_id: str,
    *,
    conn: sqlite3.Connection | None = None,
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
    if not _handler_exists(conn, tool_id) or tool_id not in pressables:
        return 'inconnu'
    if (tool_id, arguments) in deja:
        return 'deja_fait'
    cap = quota_couple(spec, tool_id, policy)
    if cap is not None and spent.get(tool_id, 0) >= cap:
        return 'quota_couple'
    return None
