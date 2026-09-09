#!/usr/bin/env python3
"""Séquenceur contact (B §2.6, familles nommées) : prochain envoi éligible.

Parcourt campagnes RUNNING (fenêtre, N, budget) → contacts QUALIFIED/
CONTACTING OUTBOUND FIFO → étape due → guards → work_item. Premier
éligible gagne. INBOUND servi par le flux réponse, pas ici. x2 voix et
attribution multi-touch avec le câblage voix/observation.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.e164 import is_valid as is_valid_phone
from serge.funnels.campaigns import n_reached, thresholds, window_open
from serge.funnels.contacts import qualify
from serge.funnels.metrics import campaign_metrics
from serge.guards import Reason, check
from serge.scheduler import enqueue

EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
SENDABLE_STATES = frozenset({'QUALIFIED', 'CONTACTING'})
SEQUENCE_DEFAULTS = {'named': 'default_named'}


class SequencerError(ValueError):
    pass


def auto_qualify(conn: sqlite3.Connection, venture_id: str) -> list[str]:
    """Pré-qualifie v1 : NEW + email/tél valide → QUALIFIED (P7 affine).

    Args:
        conn: Connexion canon (commit par l'appelant).
        venture_id: Venture scope.

    Returns:
        Ids qualifiés.
    """
    rows = conn.execute(
        'SELECT id, email, phone FROM contacts WHERE venture_id=?'
        " AND funnel_state='NEW'",
        (venture_id,),
    ).fetchall()
    qualified: list[str] = []
    for row in rows:
        email = str(row[1] or '')
        phone = str(row[2] or '')
        if (email and EMAIL_RE.match(email)) or (
            phone and is_valid_phone(phone)
        ):
            qualify(conn, str(row[0]))
            qualified.append(str(row[0]))
    return qualified


def resolve_steps(
    sequences: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    family: str,
) -> list[dict[str, Any]]:
    """Étapes : inline campagne > nommée campagne > défaut famille.

    Raises:
        SequencerError: Séquence inconnue ou malformée.
    """
    ref = thresholds.get('sequence')
    if isinstance(ref, list):
        steps = ref
    elif isinstance(ref, str):
        if ref not in sequences:
            raise SequencerError(f'séquence inconnue : {ref}')
        steps = sequences[ref]
    else:
        default = SEQUENCE_DEFAULTS.get(family)
        if not default or default not in sequences:
            raise SequencerError(f'pas de séquence par défaut : {family}')
        steps = sequences[default]
    clean: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict) or not step.get('channel'):
            raise SequencerError('étape invalide (channel requis)')
        clean.append(
            {
                'channel': str(step['channel']),
                'delay_days': int(step.get('delay_days', 0)),
            }
        )
    return clean


def _sent_touches(
    conn: sqlite3.Connection, campaign_id: str, contact_id: str
) -> list[sqlite3.Row]:
    return conn.execute(
        'SELECT created_at FROM touches WHERE campaign_id=?'
        " AND contact_id=? AND status IN ('sent','delivered')"
        ' ORDER BY created_at ASC',
        (campaign_id, contact_id),
    ).fetchall()


def step_due(
    conn: sqlite3.Connection,
    campaign_id: str,
    contact_id: str,
    steps: list[dict[str, Any]],
    now: str,
) -> dict[str, Any] | None:
    """Prochaine étape due (index = touches envoyées). None = terminé/attente.

    Args:
        conn: Connexion canon (lecture).
        campaign_id: Campagne scope.
        contact_id: Contact scope.
        steps: Étapes résolues.
        now: ISO UTC.

    Returns:
        L'étape due (+ index) ou None.
    """
    sent = _sent_touches(conn, campaign_id, contact_id)
    index = len(sent)
    if index >= len(steps):
        return None
    step = steps[index]
    if sent:
        last = datetime.fromisoformat(sent[-1][0])
        due_at = last + timedelta(days=int(step['delay_days']))
        if datetime.fromisoformat(now) < due_at:
            return None
    return {**step, 'index': index}


def _in_flight(
    conn: sqlite3.Connection, campaign_id: str, contact_id: str
) -> bool:
    row = conn.execute(
        'SELECT 1 FROM work_items WHERE campaign_id=? AND contact_id=?'
        " AND status IN ('READY','RUNNING')",
        (campaign_id, contact_id),
    ).fetchone()
    return row is not None


def _subject_for(channel: str, email: str, phone: str) -> str:
    if channel in {'voice', 'sms'}:
        return phone
    return email


def next_send(
    conn: sqlite3.Connection,
    venture_id: str,
    policy: Mapping[str, Any],
    sequences: Mapping[str, Any],
    now: str | None = None,
) -> str | None:
    """Enqueue le prochain envoi éligible (work_item id). None = rien à faire.

    Args:
        conn: Connexion canon (commit par l'appelant).
        venture_id: Venture ACTIVE scope.
        policy: Policy (guards).
        sequences: Registre sequences.yaml chargé.
        now: ISO UTC (défaut : maintenant).

    Returns:
        L'id du work_item créé, ou None.
    """
    moment = now or utcnow()
    campaigns = conn.execute(
        'SELECT id, family, channel, budget_cap_eur FROM campaigns'
        " WHERE venture_id=? AND family='named' AND state='RUNNING'"
        ' ORDER BY created_at ASC',
        (venture_id,),
    ).fetchall()
    for campaign in campaigns:
        campaign_id = str(campaign[0])
        if not window_open(conn, campaign_id, moment):
            continue
        if n_reached(conn, campaign_id):
            continue
        cap = float(campaign[3] or 0)
        if cap > 0 and campaign_metrics(conn, campaign_id)['cost_eur'] >= cap:
            continue
        steps = resolve_steps(
            sequences,
            thresholds(conn, campaign_id),
            str(campaign[1]),
        )
        contacts = conn.execute(
            'SELECT id, email, phone FROM contacts WHERE venture_id=?'
            " AND funnel_state IN ('QUALIFIED','CONTACTING')"
            " AND regime='OUTBOUND' ORDER BY created_at ASC",
            (venture_id,),
        ).fetchall()
        for contact in contacts:
            contact_id = str(contact[0])
            if _in_flight(conn, campaign_id, contact_id):
                continue
            step = step_due(conn, campaign_id, contact_id, steps, moment)
            if step is None:
                continue
            subject = _subject_for(
                step['channel'], str(contact[1] or ''), str(contact[2] or '')
            )
            if not subject:
                continue
            key = f'{campaign_id}:{contact_id}:{step["index"]}'
            verdict = check(
                conn,
                policy,
                {
                    'channel': step['channel'],
                    'subject': subject,
                    'idempotency_key': key,
                    'contact_id': contact_id,
                },
                moment,
            )
            if not verdict.allowed:
                if verdict.reason == Reason.UNKNOWN_CHANNEL:
                    raise SequencerError(
                        f'canal sans guards : {step["channel"]}'
                    )
                continue
            return enqueue(
                conn,
                kind=f'{step["channel"]}.send',
                idempotency_key=f'work:{key}',
                venture_id=venture_id,
                campaign_id=campaign_id,
                contact_id=contact_id,
                payload={
                    'channel': step['channel'],
                    'step': step['index'],
                    'subject': subject,
                },
            )
    return None
