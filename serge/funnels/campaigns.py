#!/usr/bin/env python3
"""Campagnes : 1 test sur 1 canal (N, seuils, fenêtre). Générique 3 familles.

DRAFT → READY → RUNNING ⇄ PAUSED → DONE (+ CANCELLED).
Machines spécifiques (pub REVIEW/LEARNING, lieu SCOUTED...) avec leurs
adaptateurs (phase 2). Seuils pré-enregistrés exigés avant RUN.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from typing import Any

from serge.db.store import append_event, utcnow
from serge.funnels.metrics import campaign_metrics

FAMILIES = frozenset({'named', 'ads', 'place'})
RUNNABLE_VENTURES = frozenset({'SMOKE_RUNNING', 'FULL_RUNNING', 'SCALE'})


class CampaignError(ValueError):
    pass


def _new_id() -> str:
    return f'c_{uuid.uuid4().hex[:12]}'


def _get(conn: sqlite3.Connection, campaign_id: str) -> sqlite3.Row:
    row = conn.execute(
        'SELECT id, venture_id, family, channel, state, n_target,'
        ' budget_cap_eur, window_start, window_end, thresholds_json'
        ' FROM campaigns WHERE id=?',
        (campaign_id,),
    ).fetchone()
    if not row:
        raise CampaignError(f'campagne inconnue : {campaign_id}')
    return row


def _move(
    conn: sqlite3.Connection,
    campaign_id: str,
    allowed_from: frozenset[str],
    to_state: str,
    extra: dict[str, Any] | None = None,
) -> None:
    row = _get(conn, campaign_id)
    if row['state'] not in allowed_from:
        raise CampaignError(
            f'{campaign_id} : {row["state"]} → {to_state} interdit'
        )
    conn.execute(
        'UPDATE campaigns SET state=?, updated_at=? WHERE id=?',
        (to_state, utcnow(), campaign_id),
    )
    append_event(
        conn,
        actor='campaigns',
        type=f'campaign.{to_state.lower()}',
        venture_id=row['venture_id'],
        payload={'id': campaign_id, 'from': row['state'], **(extra or {})},
        links={'campaign': campaign_id},
    )


def create_campaign(
    conn: sqlite3.Connection,
    venture_id: str,
    family: str,
    channel: str,
    n_target: int = 0,
    budget_cap_eur: float = 0.0,
    window_start: str = '',
    window_end: str = '',
    thresholds: dict[str, Any] | None = None,
    phase: str = '',
) -> str:
    """Crée une campagne DRAFT (test pré-enregistrable).

    ``phase`` smoke|full : N et seuils viennent de la policy MC.

    Raises:
        CampaignError: Famille inconnue, canal vide, fenêtre incohérente.
    """
    if family not in FAMILIES:
        raise CampaignError(f'famille inconnue : {family}')
    if not channel.strip():
        raise CampaignError('canal requis')
    if window_start and window_end and window_end <= window_start:
        raise CampaignError('fenêtre incohérente (fin <= début)')
    if n_target < 0 or budget_cap_eur < 0:
        raise CampaignError('N et budget >= 0')
    if phase in {'smoke', 'full'}:
        from serge.funnels.essai import taille_et_seuils

        n_target, thresholds = taille_et_seuils(
            conn, phase, n_target, thresholds
        )
    campaign_id = _new_id()
    moment = utcnow()
    conn.execute(
        'INSERT INTO campaigns(id, venture_id, family, channel, state,'
        ' n_target, budget_cap_eur, window_start, window_end,'
        " thresholds_json, created_at, updated_at) VALUES(?,?,?,?,'DRAFT',"
        '?,?,?,?,?,?,?)',
        (
            campaign_id,
            venture_id,
            family,
            channel,
            n_target,
            budget_cap_eur,
            window_start,
            window_end,
            json.dumps(thresholds or {}, ensure_ascii=False),
            moment,
            moment,
        ),
    )
    append_event(
        conn,
        actor='campaigns',
        type='campaign.draft',
        venture_id=venture_id,
        payload={'id': campaign_id, 'family': family, 'channel': channel},
        links={'campaign': campaign_id},
    )
    return campaign_id


def to_ready(conn: sqlite3.Connection, campaign_id: str) -> None:
    """DRAFT → READY : N > 0 + seuils pré-enregistrés exigés."""
    row = _get(conn, campaign_id)
    if int(row['n_target']) <= 0:
        raise CampaignError(f'{campaign_id} : N requis avant READY')
    if json.loads(row['thresholds_json'] or '{}') == {}:
        raise CampaignError(f'{campaign_id} : seuils pré-enregistrés requis')
    _move(conn, campaign_id, frozenset({'DRAFT'}), 'READY')


def start(conn: sqlite3.Connection, campaign_id: str) -> None:
    """READY → RUNNING : venture en test/SCALE exigée."""
    row = _get(conn, campaign_id)
    venture = conn.execute(
        'SELECT lifecycle FROM ventures WHERE id=?', (row['venture_id'],)
    ).fetchone()
    if not venture or venture[0] not in RUNNABLE_VENTURES:
        raise CampaignError(f'{campaign_id} : venture hors test/SCALE')
    _move(conn, campaign_id, frozenset({'READY'}), 'RUNNING')


def pause(conn: sqlite3.Connection, campaign_id: str) -> None:
    _move(conn, campaign_id, frozenset({'RUNNING'}), 'PAUSED')


def resume(conn: sqlite3.Connection, campaign_id: str) -> None:
    _move(conn, campaign_id, frozenset({'PAUSED'}), 'RUNNING')


def finish(
    conn: sqlite3.Connection,
    campaign_id: str,
    outcome: str,
    metrics: dict[str, Any] | None = None,
) -> None:
    """RUNNING/PAUSED → DONE + verdict enregistré (événement)."""
    _move(
        conn,
        campaign_id,
        frozenset({'RUNNING', 'PAUSED'}),
        'DONE',
        {'outcome': outcome, 'metrics': metrics or {}},
    )


def cancel(conn: sqlite3.Connection, campaign_id: str) -> None:
    _move(
        conn,
        campaign_id,
        frozenset({'DRAFT', 'READY', 'RUNNING', 'PAUSED'}),
        'CANCELLED',
    )


def window_open(
    conn: sqlite3.Connection, campaign_id: str, now: str | None = None
) -> bool:
    """Fenêtre temporelle ouverte (vide = ouverte)."""
    row = _get(conn, campaign_id)
    moment = now or utcnow()
    if row['window_start'] and moment < row['window_start']:
        return False
    if row['window_end'] and moment > row['window_end']:
        return False
    return True


def window_elapsed(
    conn: sqlite3.Connection, campaign_id: str, now: str | None = None
) -> bool:
    """Fenêtre écoulée (sans fin = jamais)."""
    row = _get(conn, campaign_id)
    if not row['window_end']:
        return False
    return (now or utcnow()) > row['window_end']


def n_reached(conn: sqlite3.Connection, campaign_id: str) -> bool:
    """N valide atteint (U1 hors INVALID >= n_target)."""
    row = _get(conn, campaign_id)
    metrics = campaign_metrics(conn, campaign_id)
    return int(metrics['n_valid']) >= int(row['n_target'])


def thresholds(conn: sqlite3.Connection, campaign_id: str) -> dict[str, Any]:
    """Seuils pré-enregistrés de la campagne."""
    row = _get(conn, campaign_id)
    data = json.loads(row['thresholds_json'] or '{}')
    return data if isinstance(data, dict) else {}
