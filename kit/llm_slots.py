#!/usr/bin/env python3
"""Render the llm slot seed from instance [llm] (T1/T2/T3 -> slots)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from kit.openrouter import RECOMMENDED_TIERS, TIER_TO_SLOT


def slots_from_llm(llm: Mapping[str, Any] | None) -> dict[str, Any]:
    """Map instance [llm] tiers to runtime slots (CHEAP/DEFAULT/SMART).

    Missing models fall back to live-tested recommendations so old TOMLs
    without tiers still build.

    Args:
        llm: The [llm] table (provider, referer, t1/t2/t3/guide models).

    Returns:
        Slot seed: provider, referer, slots, guide_model. No secrets.
    """
    data = dict(llm or {})
    tiers = {}
    for tier, default in RECOMMENDED_TIERS.items():
        value = str(data.get(f'{tier}_model') or '').strip()
        tiers[tier] = value or default
    guide = str(data.get('guide_model') or '').strip() or tiers['t2']
    return {
        'provider': str(data.get('provider') or 'openrouter'),
        'referer': str(data.get('referer') or ''),
        'slots': {
            TIER_TO_SLOT[tier]: {
                'openrouter_id': tiers[tier],
                'model_ref': f'openrouter/{tiers[tier]}',
            }
            for tier in ('t1', 't2', 't3')
        },
        'guide_model': guide,
        'secret_values_included': False,
    }


def write_llm_slots(config_root: Path, llm: Mapping[str, Any] | None) -> Path:
    """Write <config_root>/llm/slots.json (0644, no secrets inside).

    Args:
        config_root: Instance config root.
        llm: The [llm] table.

    Returns:
        Path of the written file.
    """
    dest_dir = config_root / 'llm'
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / 'slots.json'
    dest.write_text(
        json.dumps(slots_from_llm(llm), indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8',
    )
    dest.chmod(0o644)
    return dest
