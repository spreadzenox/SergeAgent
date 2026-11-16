#!/usr/bin/env python3
"""Démarrer une campagne prête.

Le volume d'une campagne vient des réglages de l'invocation qui la
démarre, un jeu par canal : ``<canal>_test`` (les prospects d'un test
léger), ``<canal>_semaine`` et ``<canal>_total`` (la prospection lourde).
Exemple : ``email_test = 40``. Un nouveau canal arrive avec ses réglages.
Un test dure ce que dit le plan du POC, au plus ``duree_max_jours``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import utcnow
from serge.interpreter.settings import load_settings
from serge.policy_store import setting_value
from serge.privacy import subject_hash

SMOKE, FULL = 'smoke', 'full'
RUNNING_STATUS = {SMOKE: 'SMOKE_RUNNING', FULL: 'FULL_RUNNING'}


def campaign(conn: sqlite3.Connection, campaign_id: str) -> dict | None:
    """Une campagne, avec la sorte d'adresse de son canal et s'il est
    branché sur ce serveur."""
    cursor = conn.execute(
        "SELECT c.*, COALESCE(k.address_channel, '') AS address_kind,"
        ' COALESCE(k.connected, 0) AS connected FROM campaigns c'
        ' LEFT JOIN canaux k ON k.id=c.channel WHERE c.id=?',
        (campaign_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return dict(zip([d[0] for d in cursor.description], row, strict=True))


def _number(settings: dict[str, str], name: str) -> int | None:
    value = str(settings.get(name, '')).strip()
    return int(value) if value.isdigit() else None


def _days(conn: sqlite3.Connection, venture: str, maximum: int) -> int:
    """La durée d'un test : celle du dernier plan validé du POC, au plus
    le maximum réglé."""
    row = conn.execute(
        "SELECT duration_days FROM product_plans WHERE venture_id=?"
        " AND kind='poc' AND status='validated'"
        ' ORDER BY created_at DESC, rowid DESC LIMIT 1',
        (venture,),
    ).fetchone()
    planned = int(row[0]) if row and int(row[0] or 0) > 0 else maximum
    return min(planned, maximum)


def _cold_refusal(conn: sqlite3.Connection, row: dict) -> str:
    """Un canal qui demande l'accord de la personne avant tout contact
    (page Policy, « Accord des gens ») ne sert pas à prospecter des
    inconnus : sans un contact de ce business qui a donné son accord, la
    campagne ne démarre pas. Rend la raison, ou ``''``."""
    channel = str(row['channel'])
    if channel not in (setting_value(conn, 'consent.opt_in_channels') or []):
        return ''
    for (address,) in conn.execute(
        'SELECT a.value_norm FROM contact_addresses a JOIN contacts c'
        ' ON c.id=a.contact_id WHERE c.venture_id=? AND a.channel=?'
        ' AND a.active=1',
        (row['venture_id'], row['address_kind']),
    ).fetchall():
        if conn.execute(
            'SELECT 1 FROM consents WHERE subject_hash=? AND channel IN'
            " (?, '*') AND revoked_at=''",
            (subject_hash(str(address)), channel),
        ).fetchone():
            return ''
    return (
        f'le canal « {channel} » demande l’accord de la personne avant tout'
        ' contact (page Policy, « Accord des gens ») : il ne sert pas à'
        ' prospecter des inconnus'
    )


def start_campaign(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Démarrer une campagne » : ``{campaign_id}``.

    Rend ce que les règles d'écriture rangent : la campagne passe à
    ``RUNNING`` avec son volume, son début et sa fin prévue, et son
    business à « test en cours » ou « vente en cours ». Une campagne dont
    le canal n'est pas branché, n'a pas de réglage de volume, ou demande
    un accord que personne n'a donné, est annulée (``CANCELLED``), avec la
    raison.
    """
    row = campaign(conn, str(args.get('campaign_id') or ''))
    if row is None or row['state'] != 'READY':
        return {'ok': False, 'state': '', 'raison': 'campagne pas prête'}
    base = {'campaign_id': row['id'], 'venture_id': row['venture_id']}
    channel, phase = str(row['channel']), str(row['phase'])
    settings = load_settings(conn, inv)
    total = _number(
        settings, f'{channel}_test' if phase == SMOKE else f'{channel}_total'
    )
    raison = ''
    if not int(row['connected']):
        raison = f'le canal « {channel} » n’est pas branché sur ce serveur'
    elif phase not in RUNNING_STATUS:
        raison = f'phase inconnue : {phase}'
    elif total is None:
        raison = f'aucun réglage de volume pour le canal « {channel} »'
    else:
        raison = _cold_refusal(conn, row)
    if raison:
        return {**base, 'ok': False, 'state': 'CANCELLED', 'raison': raison}
    now = datetime.fromisoformat(utcnow())
    answer: dict[str, Any] = {
        **base,
        'ok': True,
        'state': 'RUNNING',
        'channel': channel,
        'address_kind': row['address_kind'],
        'phase': phase,
        'n_target': total,
        'started_at': now.isoformat(),
        'venture_status': RUNNING_STATUS[phase],
    }
    if phase == SMOKE:
        days = _days(
            conn,
            str(row['venture_id']),
            _number(settings, 'duree_max_jours') or 30,
        )
        answer['planned_end_at'] = (now + timedelta(days=days)).isoformat()
    else:
        answer['n_week'] = _number(settings, f'{channel}_semaine') or total
    return answer
