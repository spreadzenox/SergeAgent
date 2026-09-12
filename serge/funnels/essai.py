#!/usr/bin/env python3
"""Taille des essais : N et seuils lus dans la policy en vigueur."""

from __future__ import annotations

import sqlite3
from typing import Any

from kit.instance_file import _validate_testing
from serge.funnels.campaigns import create_campaign
from serge.funnels.metrics import campaign_metrics
from serge.funnels.rules import evaluate_full, evaluate_smoke
from serge.policy_snapshots import policy_en_vigueur


def testing_en_vigueur(conn: sqlite3.Connection) -> dict[str, int]:
    """Bloc testing du dernier snapshot (défauts si absent)."""
    pol = policy_en_vigueur(conn)
    raw = pol.get('testing') if isinstance(pol.get('testing'), dict) else {}
    return _validate_testing(raw)


def n_et_seuils(
    testing: dict[str, int], phase: str
) -> tuple[int, dict[str, Any]]:
    """N cible + seuils kill/scale pour un smoke ou un full.

    Args:
        testing: Bloc validé (MC / snapshot).
        phase: ``smoke`` ou ``full``.

    Returns:
        (n_target, thresholds) à poser sur la campagne.
    """
    if phase == 'smoke':
        return testing['n_smoke_min'], {
            'phase': 'smoke',
            'scale_min_positifs': testing['scale_min_positives'],
        }
    if phase == 'full':
        return testing['n_full_target'], {
            'phase': 'full',
            'scale_min_positifs': testing['scale_min_positives'],
            'kill_max_positifs': testing['kill_max_positives'],
            'scale_min_meetings': testing['scale_min_meetings'],
            'extend_max': testing['extend_max'],
        }
    raise ValueError(f'phase inconnue : {phase}')


def taille_et_seuils(
    conn: sqlite3.Connection,
    phase: str,
    n_target: int,
    thresholds: dict[str, Any] | None,
) -> tuple[int, dict[str, Any]]:
    """Complète N/seuils depuis la policy si l’appelant n’a rien posé."""
    n_def, th_def = n_et_seuils(testing_en_vigueur(conn), phase)
    if n_target <= 0:
        n_target = n_def
    merged = {**th_def, **(thresholds or {})}
    return n_target, merged


def ouvrir_essai(
    conn: sqlite3.Connection,
    venture_id: str,
    family: str,
    channel: str,
    phase: str,
    **kwargs: Any,
) -> str:
    """Crée un essai dont le N et les seuils viennent de MC."""
    return create_campaign(
        conn,
        venture_id,
        family,
        channel,
        phase=phase,
        **kwargs,
    )


def evaluer_campagne(
    conn: sqlite3.Connection,
    campaign_id: str,
    *,
    n_atteint: bool,
    fenetre_ecoulee: bool,
    etendu: bool = False,
) -> str:
    """Verdict smoke/full avec les seuils stampés (ceux de MC)."""
    from serge.funnels.campaigns import thresholds

    th = thresholds(conn, campaign_id)
    metrics = campaign_metrics(conn, campaign_id)
    phase = str(th.get('phase') or 'smoke')
    if phase == 'full':
        return evaluate_full(
            metrics,
            th,
            n_reached=n_atteint,
            window_elapsed=fenetre_ecoulee,
            extended=etendu,
        )
    return evaluate_smoke(metrics, th)
