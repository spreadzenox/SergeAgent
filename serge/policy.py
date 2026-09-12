#!/usr/bin/env python3
"""Config loader: policy.yaml (+ overlay test). Fail-closed."""

from __future__ import annotations

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


def _need_ratio(data: Mapping[str, Any], dotted: str) -> None:
    _need_number(data, dotted, minimum=0.0)
    node: Any = data
    for part in dotted.split('.'):
        node = node[part]
    if node > 1.0:
        raise PolicyError(f'policy.{dotted} doit être <= 1.0')


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
        'budget.llm_eur_per_1k_tokens',
        'budget.allocator_bandit_cost_per_eur',
        'budget.test_provision_monthly_eur',
        'budget.browserbase_monthly_cap_eur',
        'quotas.email_per_mailbox_per_day',
        'quotas.voice_max_calls_per_day',
        'quotas.sms_per_sender_per_min',
        'quotas.sms_global_per_min',
        'quotas.memory_search_per_cycle_per_point',
        'quotas.llm_recalls_json',
        'quotas.linkedin_connect_per_day',
        'quotas.linkedin_inmail_per_month',
        'windows.intent_sla_hours',
        'cooldowns.inbound_silence_days',
        'cooldowns.thread_days_per_venue',
        'cooldowns.guichet_repropose_max',
        'voice.record_retention_hot_days',
        'voice.record_retention_archive_years',
        'voice.quality_window',
        'voice.quality_min_score',
        'voice.quality_max_bad',
        'voice.max_turns',
        'voice.max_duration_min',
        'voice.script_max_seconds',
        'observation.classify_confidence_min',
        'observation.meeting_confidence_min',
        'observation.other_batch_max_items',
        'observation.other_alert_pending',
        'observation.tech_fail_pattern_per_week',
        'builder.fix_max_items',
        'builder.passes_max',
        'builder.gate3_spotcheck_n',
        'builder.artifact_max_files',
        'builder.artifact_max_chars',
        'prospection.qualify_confidence_min',
        'prospection.score_w_intent',
        'prospection.score_w_reply',
        'prospection.score_w_engaged',
        'prospection.score_w_meeting',
        'collect.refund_auto_max_eur',
        'collect.draft_price_min_eur',
        'collect.draft_price_max_eur',
        'collect.quote_required_above_eur',
        'collect.recanary_months',
        'memory.consolidation_days',
        'memory.consolidate_max_items',
        'memory.lesson_infirm_deprecate',
        'memory.episode_archive_days',
        'memory.other_promote_per_week',
        'memory.judge_oscillation_days',
        'memory.serge_md_max_lines',
        'tickets.digest_hour',
        'tickets.trust_min_approvals',
        'listen.cluster_jaccard_min',
    ):
        _need_number(data, key)
    for key in (
        'budget.allocator_reserve_ratio',
        'budget.allocator_max_unproven_ratio',
        'budget.allocator_max_single_channel_ratio',
        'budget.allocator_trigger_spent_ratio',
        'tickets.trust_min_rate',
        'listen.hot_min_volume',
        'listen.hot_min_willingness',
    ):
        _need_ratio(data, key)
    _need_number(data, 'prospection.score_w_negative', minimum=-100.0)
    _need_str_list(data, 'consent.opt_in_channels')
    zones = data.get('calling_zones')
    if not isinstance(zones, Mapping) or not zones.get('default'):
        raise PolicyError('policy.calling_zones.default manquant')
    default = zones['default']
    if default not in zones or not isinstance(zones[default], Mapping):
        raise PolicyError(f'policy.calling_zones.{default} manquante')
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
