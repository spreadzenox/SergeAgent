#!/usr/bin/env python3
"""Schémas OpenAI dérivés des contrats des tools DB."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def _schema_type(kind: str) -> str:
    return {
        'string': 'string',
        'integer': 'integer',
        'number': 'number',
        'boolean': 'boolean',
        'array': 'array',
    }.get(kind, 'string')


def build_openai_schema(
    catalogue: Mapping[str, Any], tool_id: str
) -> dict[str, Any]:
    """Construit le schéma function depuis le catalogue relationnel."""
    columns = [
        f'{item["table"]}.{item["name"]}' for item in catalogue['columns']
    ]
    tables = [str(item['name']) for item in catalogue['tables']]
    join_columns = sorted({str(item['name']) for item in catalogue['columns']})
    properties: dict[str, Any] = {
        'columns': {
            'type': 'array',
            'items': {'type': 'string', 'enum': columns},
            'description': 'Colonnes déclarées à retourner.',
        },
        'joins': {
            'type': 'array',
            'description': 'Jointures demandées entre tables et colonnes autorisées.',
            'items': {
                'type': 'object',
                'properties': {
                    'left_table': {'type': 'string', 'enum': tables},
                    'left_column': {'type': 'string', 'enum': join_columns},
                    'right_table': {'type': 'string', 'enum': tables},
                    'right_column': {'type': 'string', 'enum': join_columns},
                },
                'required': [
                    'left_table',
                    'left_column',
                    'right_table',
                    'right_column',
                ],
                'additionalProperties': False,
            },
        },
    }
    required: list[str] = []
    for parameter in catalogue['params']:
        name = str(parameter['name'])
        prop: dict[str, Any] = {
            'type': _schema_type(str(parameter['type'])),
            'description': str(parameter['description']),
        }
        enum = catalogue['param_enums'].get(name) or []
        if enum:
            prop['enum'] = enum
        if prop['type'] == 'array':
            prop['items'] = {'type': 'string'}
        properties[name] = prop
        if parameter['required'] and not parameter['default_text']:
            required.append(name)
    return {
        'type': 'function',
        'function': {
            'name': tool_id,
            'description': catalogue['description'] or catalogue['titre'],
            'parameters': {
                'type': 'object',
                'properties': properties,
                'required': required,
                'additionalProperties': False,
            },
        },
    }
