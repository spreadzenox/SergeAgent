#!/usr/bin/env python3
"""Validation et conversion des paramètres des tools DB."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from serge.db.query_errors import DbReadError


def coerce(value: Any, parameter: Mapping[str, Any]) -> Any:
    kind = str(parameter['type'])
    if kind == 'string':
        if not isinstance(value, str):
            raise DbReadError(
                f'paramètre {parameter["name"]} doit être une chaîne'
            )
        return value
    if kind == 'integer':
        if isinstance(value, bool) or not isinstance(value, int):
            raise DbReadError(
                f'paramètre {parameter["name"]} doit être un entier'
            )
        return value
    if kind == 'number':
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DbReadError(
                f'paramètre {parameter["name"]} doit être un nombre'
            )
        return value
    if kind == 'boolean':
        if not isinstance(value, bool):
            raise DbReadError(
                f'paramètre {parameter["name"]} doit être booléen'
            )
        return value
    if kind == 'array':
        if not isinstance(value, list) or any(
            isinstance(item, (dict, list)) for item in value
        ):
            raise DbReadError(
                f'paramètre {parameter["name"]} doit être une liste simple'
            )
        return value
    raise DbReadError(f'type de paramètre inconnu: {kind}')


def default(parameter: Mapping[str, Any]) -> Any:
    raw = str(parameter.get('default_text') or '')
    if not raw:
        return None
    kind = str(parameter['type'])
    if kind == 'string':
        return raw
    if kind == 'integer':
        try:
            return int(raw)
        except ValueError as exc:
            raise DbReadError(
                f'défaut entier invalide: {parameter["name"]}'
            ) from exc
    if kind == 'number':
        try:
            return float(raw)
        except ValueError as exc:
            raise DbReadError(
                f'défaut numérique invalide: {parameter["name"]}'
            ) from exc
    if kind == 'boolean':
        if raw not in {'true', 'false'}:
            raise DbReadError(f'défaut booléen invalide: {parameter["name"]}')
        return raw == 'true'
    raise DbReadError(f'défaut non supporté: {parameter["name"]}')
