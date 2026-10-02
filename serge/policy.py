#!/usr/bin/env python3
"""Config loader: policy.yaml (+ overlay test). Fail-closed."""

from __future__ import annotations

import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1


class PolicyError(ValueError):
    """Config invalide ou illisible : le boot doit refuser."""


def config_dir() -> Path:
    """Dossier config (override SERGE_CONFIG_DIR pour les tests).

    Returns:
        Chemin du dossier contenant policy.yaml et registres.
    """
    override = os.environ.get('SERGE_CONFIG_DIR', '').strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / 'config'


def is_test_env() -> bool:
    """True quand SERGE_ENV=test (policy test + allowlist, jamais prod).

    Returns:
        True si l'environnement de test live-prudent est actif.
    """
    return os.environ.get('SERGE_ENV', '').strip().lower() == 'test'


def read_yaml_file(path: Path) -> dict[str, Any]:
    """Lit un YAML de config (mapping racine exigé).

    Args:
        path: Fichier à lire.

    Returns:
        Le mapping racine.

    Raises:
        PolicyError: Si illisible, invalide, ou racine non-mapping.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except OSError as exc:
        raise PolicyError(f'config illisible : {path}') from exc
    except yaml.YAMLError as exc:
        raise PolicyError(f'config YAML invalide : {path}') from exc
    if not isinstance(data, dict):
        raise PolicyError(f'config racine invalide : {path}')
    return data


def _deep_merge(base: dict[str, Any], over: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in over.items():
        if (
            key in merged
            and isinstance(merged[key], dict)
            and isinstance(value, dict)
        ):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _need_number(
    data: Mapping[str, Any], dotted: str, *, minimum: float = 0.0
) -> None:
    node: Any = data
    for part in dotted.split('.'):
        if not isinstance(node, Mapping) or part not in node:
            raise PolicyError(f'policy.{dotted} manquant')
        node = node[part]
    if isinstance(node, bool) or not isinstance(node, (int, float)):
        raise PolicyError(f'policy.{dotted} doit être un nombre')
    if isinstance(node, float) and not math.isfinite(node):
        raise PolicyError(f'policy.{dotted} doit être un nombre fini')
    if node < minimum:
        raise PolicyError(f'policy.{dotted} doit être >= {minimum}')


def _need_str_list(data: Mapping[str, Any], dotted: str) -> None:
    node: Any = data
    for part in dotted.split('.'):
        if not isinstance(node, Mapping) or part not in node:
            raise PolicyError(f'policy.{dotted} manquant')
        node = node[part]
    if not isinstance(node, list) or not all(
        isinstance(item, str) and item for item in node
    ):
        raise PolicyError(f'policy.{dotted} doit être une liste de chaînes')


def validate_policy(data: Mapping[str, Any]) -> dict[str, Any]:
    """Valide la policy fusionnée. Refuse l'absurde au boot (R4).

    Args:
        data: Policy (base + overlay test éventuel).

    Returns:
        La policy validée (copie).

    Raises:
        PolicyError: Si schéma, type ou plage invalide.
    """
    if data.get('schema_version') != SCHEMA_VERSION:
        raise PolicyError('policy.schema_version doit valoir 1')
    for key in (
        'budget.monthly_eur',
        'budget.llm_daily_eur',
        'budget.eur_per_usd',
        'quotas.email_per_mailbox_per_day',
        'quotas.voice_max_calls_per_day',
        'quotas.sms_per_sender_per_min',
        'quotas.sms_global_per_min',
        'quotas.llm_recalls_json',
        'quotas.llm_outil_resultat_max_caracteres',
        'quotas.linkedin_connect_per_day',
        'standing.cout_usage',
        'standing.gain_par_heure',
        'standing.idle_apres_heures',
        'standing.capital_min',
        'standing.capital_max',
        'voice.quality_window',
        'voice.quality_min_score',
        'voice.quality_max_bad',
        'collect.refund_auto_max_eur',
        'memory.episode_archive_days',
        'tickets.digest_hour',
        'testing.n_smoke_min',
        'testing.n_smoke_max',
        'testing.n_full_min',
        'testing.n_full_target',
        'testing.kill_max_positives',
        'testing.scale_min_positives',
        'testing.scale_min_meetings',
        'testing.extend_max',
    ):
        _need_number(data, key)
    _need_str_list(data, 'consent.opt_in_channels')
    standing = data.get('standing')
    if isinstance(standing, Mapping):
        if standing.get('capital_max', 0) < standing.get('capital_min', 0):
            raise PolicyError('policy.standing.capital_max < capital_min')
    zones = data.get('calling_zones')
    if not isinstance(zones, Mapping) or not zones.get('default'):
        raise PolicyError('policy.calling_zones.default manquant')
    default = zones['default']
    if default not in zones or not isinstance(zones[default], Mapping):
        raise PolicyError(f'policy.calling_zones.{default} manquante')
    from kit.instance_file import InstanceError, _validate_testing

    testing = data.get('testing') or {}
    try:
        _validate_testing(testing)
    except InstanceError as exc:
        raise PolicyError(f'policy.testing : {exc}') from exc
    return dict(data)


def load_policy(directory: Path | None = None) -> dict[str, Any]:
    """Semence YAML (graine git). Runtime = dernier snapshot du canon.

    Args:
        directory: Dossier config (défaut : config du repo).

    Returns:
        Policy fusionnée et validée.

    Raises:
        PolicyError: Si illisible ou invalide.
    """
    root = directory or config_dir()
    policy = read_yaml_file(root / 'policy.yaml')
    if is_test_env():
        overlay = read_yaml_file(root / 'policy.test.yaml')
        if overlay.pop('extends', 'policy.yaml') != 'policy.yaml':
            raise PolicyError('policy.test.yaml doit étendre policy.yaml')
        policy = _deep_merge(policy, overlay)
    return validate_policy(policy)


def _keep_seeded(seed: Mapping[str, Any], data: Mapping[str, Any]) -> dict:
    """Les clés de ``data`` que la semence connaît, à tous les niveaux."""
    return {
        key: _keep_seeded(seed[key], value)
        if isinstance(seed[key], dict) and isinstance(value, dict)
        else value
        for key, value in data.items()
        if key in seed
    }


def fusionner_semence(data: Mapping[str, Any]) -> dict[str, Any]:
    """Complète un snapshot avec les clés nouvelles de la semence YAML.

    Un réglage ou une section retirés de la semence disparaissent aussi de
    la policy en vigueur. Exemple : au 1er octobre 2026, les réglages que
    rien ne lisait ont été retirés (décision Q68) ; un ancien snapshot qui
    les contient encore ne les affiche plus dans Mission Control.

    Args:
        data: Snapshot (les valeurs présentes gagnent).

    Returns:
        Policy fusionnée, pas encore revalidée.
    """
    semence = load_policy()
    return _keep_seeded(semence, _deep_merge(semence, dict(data)))
