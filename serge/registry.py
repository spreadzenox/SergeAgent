#!/usr/bin/env python3
"""Le registre des types de tickets (``config/ticket-types.yaml``)."""

from __future__ import annotations

from pathlib import Path

from serge.policy import (
    SCHEMA_VERSION,
    PolicyError,
    config_dir,
    read_yaml_file,
)


def _load_registry(filename: str, directory: Path | None = None) -> dict:
    root = directory or config_dir()
    data = read_yaml_file(root / filename)
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PolicyError(f'{filename} : schema_version doit valoir 1')
    return data


def load_ticket_types(directory: Path | None = None) -> dict[str, dict]:
    """Charge et valide les types de tickets.

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping type de ticket → déclaration validée.

    Raises:
        PolicyError: Si type incomplet.
    """
    data = _load_registry('ticket-types.yaml', directory)
    types = data.get('types')
    if not isinstance(types, dict) or not types:
        raise PolicyError('ticket-types.yaml : types manquants')
    for name, spec in types.items():
        if not isinstance(spec, dict):
            raise PolicyError(f'ticket-types.{name} invalide')
        for key in ('role', 'urgency', 'default', 'fields', 'buttons'):
            if key not in spec:
                raise PolicyError(f'ticket-types.{name}.{key} manquant')
        if 'expiry_hours' not in spec and 'expiry_minutes' not in spec:
            raise PolicyError(f'ticket-types.{name} : expiry manquante')
        render = spec.get('render')
        if render is not None:
            if not isinstance(render, dict):
                raise PolicyError(f'ticket-types.{name}.render invalide')
            color = render.get('color')
            if (
                isinstance(color, bool)
                or not isinstance(color, int)
                or not 0 <= color <= 0xFFFFFF
            ):
                raise PolicyError(f'ticket-types.{name}.render.color invalide')
            if not render.get('emoji') or not isinstance(
                render.get('emoji'), str
            ):
                raise PolicyError(f'ticket-types.{name}.render.emoji invalide')
    return types
