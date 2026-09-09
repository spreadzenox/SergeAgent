#!/usr/bin/env python3
"""Registres versionnés: points LLM (C), tickets (H), séquences (B §2.6)."""

from __future__ import annotations

from pathlib import Path

from serge.policy import (
    SCHEMA_VERSION,
    PolicyError,
    config_dir,
    read_yaml_file,
)

VERDICTS = frozenset({'LLM-1', 'LLM-B', 'LLM-L', 'LLM-R', 'HYB'})
TIERS = frozenset({'T1', 'T2', 'T3'})


def _load_registry(filename: str, directory: Path | None = None) -> dict:
    root = directory or config_dir()
    data = read_yaml_file(root / filename)
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PolicyError(f'{filename} : schema_version doit valoir 1')
    return data


def load_llm_points(directory: Path | None = None) -> dict[str, dict]:
    """Charge et valide le registre des points LLM (matrice C).

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping nom de point → déclaration validée.

    Raises:
        PolicyError: Si point incomplet (verdict/tier/contrat/garde-fou).
    """
    data = _load_registry('llm-points.yaml', directory)
    points = data.get('points')
    if not isinstance(points, dict) or not points:
        raise PolicyError('llm-points.yaml : points manquants')
    for name, point in points.items():
        if not isinstance(point, dict):
            raise PolicyError(f'llm-points.{name} invalide')
        if point.get('verdict') not in VERDICTS:
            raise PolicyError(f'llm-points.{name}.verdict invalide')
        if point.get('tier') not in TIERS:
            raise PolicyError(f'llm-points.{name}.tier invalide')
        context = point.get('context')
        if not isinstance(context, dict):
            raise PolicyError(f'llm-points.{name}.context manquant')
        for key in ('fixed', 'retrieved', 'couche5', 'forbidden'):
            if key not in context:
                raise PolicyError(f'llm-points.{name}.context.{key} manquant')
        envelope = context.get('envelope_tokens', 0)
        if isinstance(envelope, bool) or not isinstance(envelope, int):
            raise PolicyError(f'llm-points.{name}.envelope_tokens invalide')
        if not isinstance(point.get('enabled'), bool):
            raise PolicyError(f'llm-points.{name}.enabled doit être booléen')
        for key in ('checklist', 'garde_fou', 'repli'):
            if not point.get(key):
                raise PolicyError(f'llm-points.{name}.{key} manquant')
    return points


def llm_enabled(name: str, directory: Path | None = None) -> bool:
    """Kill-switch par point (matrice C §0). Fallback dét si False.

    Args:
        name: Nom du point (ex. qualify_prospect).
        directory: Dossier config (défaut : config du repo).

    Returns:
        True si le point est activé, False si inconnu ou coupé.
    """
    try:
        points = load_llm_points(directory)
    except PolicyError:
        return False
    point = points.get(name)
    return bool(isinstance(point, dict) and point.get('enabled') is True)


def load_ticket_types(directory: Path | None = None) -> dict[str, dict]:
    """Charge et valide la taxonomie des tickets (H §0, §7).

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


def load_sequences(directory: Path | None = None) -> dict[str, list]:
    """Charge et valide les séquences de prospection (B §2.6).

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Mapping nom → étapes [{channel, delay_days}].

    Raises:
        PolicyError: Si étape incomplète.
    """
    data = _load_registry('sequences.yaml', directory)
    sequences = data.get('sequences')
    if not isinstance(sequences, dict) or not sequences:
        raise PolicyError('sequences.yaml : sequences manquantes')
    for name, steps in sequences.items():
        if not isinstance(steps, list) or not steps:
            raise PolicyError(f'sequences.{name} invalide')
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise PolicyError(f'sequences.{name}[{index}] invalide')
            channel = step.get('channel')
            delay = step.get('delay_days')
            if not channel or not isinstance(channel, str):
                raise PolicyError(f'sequences.{name}[{index}].channel requis')
            if isinstance(delay, bool) or not isinstance(delay, int):
                raise PolicyError(
                    f'sequences.{name}[{index}].delay_days doit être entier'
                )
            if delay < 0:
                raise PolicyError(f'sequences.{name}[{index}].delay_days >= 0')
    return sequences
