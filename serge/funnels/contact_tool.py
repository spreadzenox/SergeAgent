#!/usr/bin/env python3
"""Tool ``contact_upsert`` : schéma présenté au modèle et exécution."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.contacts import ContactError, upsert_contact


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
    'Crée la fiche d’un prospect, ou ajoute des adresses à sa fiche. '
    'Une adresse déjà connue dans ce business désigne la même personne ; '
    'une boîte partagée (contact@, info@…) ne regroupe jamais.',
    {
        'venture_id': {
            'type': 'string',
            'description': 'Identifiant du business dans le contexte courant',
        },
        'display': {
            'type': 'string',
            'description': 'Nom affiché du contact, sans secret',
        },
        'addresses': {
            'type': 'array',
            'description': (
                'Les adresses de la personne. Exemples : '
                "{'channel':'email','value':'ada@acme.fr'}, "
                "{'channel':'phone','value':'+33612345678'}, "
                "{'channel':'linkedin','value':'https://linkedin.com/in/ada'}."
            ),
            'minItems': 1,
            'items': {
                'type': 'object',
                'properties': {
                    'channel': {'type': 'string'},
                    'value': {'type': 'string'},
                    'active': {'type': 'boolean'},
                },
                'required': ['channel', 'value'],
                'additionalProperties': False,
            },
        },
    },
    ['venture_id', 'display', 'addresses'],
)
SCHEMA['function']['parameters']['additionalProperties'] = False


def executer_contact_upsert(
    conn: sqlite3.Connection,
    spec: Mapping[str, Any],
    args: dict[str, Any],
) -> dict[str, Any]:
    """Crée ou complète une fiche contact à partir de ses adresses."""
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
    raw = args.get('addresses')
    if not isinstance(raw, list) or not all(
        isinstance(item, Mapping) for item in raw
    ):
        return {
            'ok': False,
            'code': 'invalide',
            'detail': 'addresses doit être une liste d’objets',
        }
    try:
        return upsert_contact(conn, venture_id, display, raw)
    except ContactError as exc:
        return {'ok': False, 'code': 'invalide', 'detail': str(exc)}
