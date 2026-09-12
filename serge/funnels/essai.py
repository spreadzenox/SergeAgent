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
    """Bloc testing du dernier snapshot (défauts si absent).

    Args:
        conn: Canon (lecture, éventuellement semence).

    Returns:
        N et seuils validés (`n_smoke_min`, `n_full_target`, …).
    """
    pol = policy_en_vigueur(conn)
    bloc = pol.get('testing')
    raw: dict[str, Any] = bloc if isinstance(bloc, dict) else {}
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

    Raises:
        ValueError: Phase autre que ``smoke`` ou ``full``.
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
    """Complète N/seuils depuis la policy si l’appelant n’a rien posé.

    Args:
        conn: Canon.
        phase: ``smoke`` ou ``full``.
        n_target: N demandé (0 = prendre le défaut policy).
        thresholds: Seuils déjà posés (fusionnés par-dessus les défauts).

    Returns:
        (n_target, thresholds) prêts pour `create_campaign`.
    """
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
    """Crée un essai dont le N et les seuils viennent de MC.

    Args:
        conn: Canon.
        venture_id: Venture porteuse.
        family: ``named`` / ``ads`` / ``place``.
        channel: Canal (email, …).
        phase: ``smoke`` ou ``full``.
        **kwargs: Passé à `create_campaign` (`n_target` / `thresholds`
            optionnels : 0 ou absent = policy).

    Returns:
        Id de campagne DRAFT.
    """
    n_req = int(kwargs.pop('n_target', 0) or 0)
    th_req = kwargs.pop('thresholds', None)
    if th_req is not None and not isinstance(th_req, dict):
        th_req = None
    n_target, thresholds = taille_et_seuils(conn, phase, n_req, th_req)
    return create_campaign(
        conn,
        venture_id,
        family,
        channel,
        n_target=n_target,
        thresholds=thresholds,
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
    """Verdict smoke/full avec les seuils stampés (ceux de MC).

    Args:
        conn: Canon.
        campaign_id: Campagne à juger.
        n_atteint: N cible atteint.
        fenetre_ecoulee: Fenêtre de test close.
        etendu: Déjà prolongé (full seulement).

    Returns:
        Code règle (`FULL`, `KILL`, `SCALE`, `EXTEND`, …).
    """
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
