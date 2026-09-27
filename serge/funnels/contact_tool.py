#!/usr/bin/env python3
"""Tool ``contact_upsert`` : schéma présenté au modèle et exécution."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.contacts import ContactError, upsert_contact_references


def _schema(
    name: str, description: str, properties: dict, required: list[str]
) -> dict[str, Any]:
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


SCHEMA: dict[str, Any] = _schema(
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
)
SCHEMA['function']['parameters'].update(
    {
        'additionalProperties': False,
        'anyOf': [
            {'required': ['contact_reference_by_canal']},
            {'required': ['reference']},
        ],
    }
)


def executer_contact_upsert(
    conn: sqlite3.Connection,
    spec: Mapping[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Upsert contact borné aux références JSON canoniques."""
    forbidden = {'email', 'phone', 'venue', 'handle', 'profile_url'}
    if forbidden.intersection(args):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'les anciennes colonnes de contact sont interdites',
        }
    context = spec.get('context')
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
        conn.execute(
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
        return upsert_contact_references(conn, venture_id, display, references)
    except (ContactError, TypeError, ValueError) as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
