#!/usr/bin/env python3
"""Règles kill/scale : pures (métriques + seuils → verdict). 0 DB, 0 LLM.

Smoke (B §1) : jamais de KILL. ≥ scale_min_positifs → SCALE précoce,
sinon FULL. Full : INVALID (infra) > SCALE > EXTEND (1×, de la vie) >
PIVOT (on apprend ailleurs) > KILL. RUNNING tant que N/fenêtre incomplets.
"""

from __future__ import annotations

from typing import Any

SMOKE_DEFAULTS = {'scale_min_positifs': 3}
FULL_DEFAULTS = {
    'scale_min_positifs': 10,
    'scale_max_u4': 15.0,
    'kill_max_positifs': 2,
    'pivot_min_classes': 3,
    'invalid_bounce_rate': 0.05,
}


def evaluate_smoke(
    metrics: dict[str, Any], thresholds: dict[str, Any] | None = None
) -> str:
    """Verdict smoke : SCALE (précoce) ou FULL. Jamais KILL.

    Args:
        metrics: Sortie campaign_metrics (positifs requis).
        thresholds: Seuils pré-enregistrés (défaut : 3 positifs).

    Returns:
        'SCALE' ou 'FULL'.
    """
    merged = {**SMOKE_DEFAULTS, **(thresholds or {})}
    if int(metrics.get('positifs', 0)) >= int(merged['scale_min_positifs']):
        return 'SCALE'
    return 'FULL'


def evaluate_full(
    metrics: dict[str, Any],
    thresholds: dict[str, Any] | None = None,
    *,
    n_reached: bool,
    window_elapsed: bool,
    extended: bool,
) -> str:
    """Verdict full : RUNNING | SCALE | EXTEND | PIVOT | KILL | INVALID.

    Args:
        metrics: Sortie campaign_metrics (positifs, u4_eur, u5_classes,
            bounce_rate requis).
        thresholds: Seuils pré-enregistrés de la campagne.
        n_reached: N valide atteint.
        window_elapsed: Fenêtre écoulée.
        extended: EXTEND déjà consommé (1× max).

    Returns:
        Le verdict déterministe.
    """
    if not (n_reached and window_elapsed):
        return 'RUNNING'
    merged = {**FULL_DEFAULTS, **(thresholds or {})}
    positifs = int(metrics.get('positifs', 0))
    u4 = float(metrics.get('u4_eur', 0.0))
    u5 = int(metrics.get('u5_classes', 0))
    bounce = float(metrics.get('bounce_rate', 0.0))
    if bounce > float(merged['invalid_bounce_rate']):
        return 'INVALID'
    if positifs >= int(merged['scale_min_positifs']) and u4 <= float(
        merged['scale_max_u4']
    ):
        return 'SCALE'
    if not extended and positifs > int(merged['kill_max_positifs']):
        return 'EXTEND'
    if u5 >= int(merged['pivot_min_classes']):
        return 'PIVOT'
    return 'KILL'
