#!/usr/bin/env python3
"""Garde de santé d’un compte standing : codes fermés, capital appliqué."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from typing import Any

from serge.horloge import iso_utc
from serge.policy import load_policy

CODES_REFUS = frozenset({'inconnu', 'inactif', 'pause', 'capital'})

_UTC = UTC


class SanteError(ValueError):
    """Accès refusé. ``code`` ∈ ``CODES_REFUS``."""

    def __init__(self, code: str, compte_id: str = '') -> None:
        if code not in CODES_REFUS:
            raise ValueError(f'code de refus inconnu : {code}')
        self.code = code
        self.compte_id = compte_id
        super().__init__(code)


def _bareme(policy: dict[str, Any] | None) -> dict[str, float]:
    bloc = (policy or load_policy()).get('standing') or {}
    return {
        'cout_usage': float(bloc['cout_usage']),
        'gain_par_heure': float(bloc['gain_par_heure']),
        'idle_apres_heures': float(bloc['idle_apres_heures']),
        'capital_min': float(bloc['capital_min']),
        'capital_max': float(bloc['capital_max']),
    }


def _quand(iso: str) -> datetime | None:
    brut = iso.strip()
    if not brut:
        return None
    try:
        moment = datetime.fromisoformat(brut)
    except ValueError:
        return None
    if moment.tzinfo is None:
        return moment.replace(tzinfo=_UTC)
    return moment.astimezone(_UTC)


def _heures(depuis: str, maintenant: str) -> float:
    debut = _quand(depuis)
    fin = _quand(maintenant)
    if debut is None or fin is None:
        return 0.0
    return max(0.0, (fin - debut).total_seconds() / 3600.0)


def _lire(conn: sqlite3.Connection, compte_id: str) -> sqlite3.Row | None:
    avant = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        return conn.execute(
            'SELECT id, status, capital, cooldown_until, last_used_at'
            ' FROM accounts_standing WHERE id=?',
            (compte_id,),
        ).fetchone()
    finally:
        conn.row_factory = avant


def recuperer(
    conn: sqlite3.Connection,
    compte_id: str,
    *,
    maintenant: str | None = None,
    policy: dict[str, Any] | None = None,
) -> float:
    """Remonte le capital si le compte a assez chômé. Jamais au-dessus du max.

    Args:
        conn: Canon (commit par l’appelant).
        compte_id: Ligne ``accounts_standing``.
        maintenant: Horodatage ISO (défaut : maintenant).
        policy: Policy (défaut : semence).

    Returns:
        Capital après récupération (inchangé si inconnu ou trop tôt).
    """
    row = _lire(conn, compte_id)
    if row is None:
        return 0.0
    bareme = _bareme(policy)
    instant = maintenant or iso_utc()
    capital = float(row['capital'])
    dernier = str(row['last_used_at'] or '')
    if dernier:
        creux = _heures(dernier, instant)
        if creux >= bareme['idle_apres_heures']:
            capital = min(
                bareme['capital_max'],
                capital + creux * bareme['gain_par_heure'],
            )
            conn.execute(
                'UPDATE accounts_standing SET capital=?, updated_at=?'
                ' WHERE id=?',
                (capital, instant, compte_id),
            )
    return capital


def etat(
    conn: sqlite3.Connection,
    compte_id: str,
    *,
    maintenant: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """État typé. Récupère le capital idle, ne refuse pas.

    Args:
        conn: Canon (commit par l’appelant).
        compte_id: Ligne ``accounts_standing``.
        maintenant: Horodatage ISO (défaut : maintenant).
        policy: Policy (défaut : semence).

    Returns:
        ``code`` ∈ {``ok``} ∪ ``CODES_REFUS``, plus capital et pause.
    """
    instant = maintenant or iso_utc()
    row = _lire(conn, compte_id)
    if row is None:
        return {
            'code': 'inconnu',
            'compte_id': compte_id,
            'capital': 0.0,
            'pause_jusqua': '',
        }
    capital = recuperer(conn, compte_id, maintenant=instant, policy=policy)
    row = _lire(conn, compte_id)
    assert row is not None
    pause = str(row['cooldown_until'] or '')
    statut = str(row['status'] or '')
    bareme = _bareme(policy)
    fin_pause = _quand(pause)
    instant_dt = _quand(instant)
    if statut != 'active':
        code = 'inactif'
    elif pause and (
        fin_pause is None
        or (instant_dt is not None and fin_pause > instant_dt)
    ):
        code = 'pause'
    elif capital < bareme['capital_min']:
        code = 'capital'
    else:
        code = 'ok'
    return {
        'code': code,
        'compte_id': compte_id,
        'capital': capital,
        'pause_jusqua': pause,
    }


def autoriser(
    conn: sqlite3.Connection,
    compte_id: str,
    *,
    maintenant: str | None = None,
    policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Refuse par code si le compte n’est pas sain. Insister ne passe pas.

    Args:
        conn: Canon (commit par l’appelant).
        compte_id: Ligne ``accounts_standing``.
        maintenant: Horodatage ISO (défaut : maintenant).
        policy: Policy (défaut : semence).

    Returns:
        L’état (``code`` = ``ok``).

    Raises:
        SanteError: Compte inconnu, inactif, en pause, ou capital trop bas.
    """
    vu = etat(conn, compte_id, maintenant=maintenant, policy=policy)
    if vu['code'] != 'ok':
        raise SanteError(str(vu['code']), compte_id)
    return vu


def consommer(
    conn: sqlite3.Connection,
    compte_id: str,
    *,
    maintenant: str | None = None,
    policy: dict[str, Any] | None = None,
) -> float:
    """Après un acte autorisé : le capital ne peut que baisser.

    Args:
        conn: Canon (commit par l’appelant).
        compte_id: Ligne ``accounts_standing``.
        maintenant: Horodatage ISO (défaut : maintenant).
        policy: Policy (défaut : semence).

    Returns:
        Capital après débit.

    Raises:
        SanteError: Même refus qu’``autoriser``.
    """
    autoriser(conn, compte_id, maintenant=maintenant, policy=policy)
    bareme = _bareme(policy)
    instant = maintenant or iso_utc()
    row = _lire(conn, compte_id)
    assert row is not None
    capital = max(0.0, float(row['capital']) - bareme['cout_usage'])
    conn.execute(
        'UPDATE accounts_standing SET capital=?, last_used_at=?,'
        ' updated_at=? WHERE id=?',
        (capital, instant, instant, compte_id),
    )
    return capital
