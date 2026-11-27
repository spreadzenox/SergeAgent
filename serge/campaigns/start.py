#!/usr/bin/env python3
"""Démarrer une campagne prête.

Le volume d'une campagne vient des réglages de l'invocation qui la
démarre, un jeu par canal : ``<canal>_test`` (les prospects d'un test
léger), ``<canal>_semaine`` et ``<canal>_total`` (la prospection lourde).
Exemple : ``email_test = 40``. Un nouveau canal arrive avec ses réglages.
Un test dure ce que dit le plan du POC, au plus ``duree_max_jours``.

Un plan peut nommer plusieurs canaux, séparés par une virgule (« email,
linkedin ») : une campagne n'a qu'un canal, donc celle du plan garde le
premier, et une campagne sœur, prête, s'ouvre pour chacun des autres
(décision Q116). Chacune a son volume et se suit seule ; le test du
business est mesuré quand la dernière est close.
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Any

from serge.db.store import append_event, utcnow
from serge.interpreter.settings import load_settings
from serge.interpreter.triggers import notify_rows_written
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


def open_sisters(
    conn: sqlite3.Connection, row: dict, channels: list[str], inv: str
) -> list[str]:
    """Ouvre une campagne prête par canal de ``channels``, sœur de ``row``
    (même business, même phase, même cible) ; rend leurs numéros.

    Un canal qui a déjà sa campagne pour ce business et cette phase est
    sauté. Les campagnes ouvertes réveillent « Démarrer une campagne ».
    """
    now = utcnow()
    opened = []
    for channel in dict.fromkeys(channels):
        if conn.execute(
            'SELECT 1 FROM campaigns WHERE venture_id=? AND phase=?'
            ' AND channel=?',
            (row['venture_id'], row['phase'], channel),
        ).fetchone():
            continue
        sister = {
            name: value
            for name, value in row.items()
            if name not in ('address_kind', 'connected')
        }
        sister.update(
            id=f'cam_{uuid.uuid4().hex[:12]}',
            channel=channel,
            state='READY',
            created_at=now,
            updated_at=now,
        )
        conn.execute(
            f'INSERT INTO campaigns({", ".join(sister)})'
            f' VALUES({", ".join("?" * len(sister))})',
            list(sister.values()),
        )
        opened.append(str(sister['id']))
    if opened:
        append_event(
            conn,
            actor=f'invocation:{inv}',
            type='campaign.sisters_opened',
            venture_id=str(row['venture_id']),
            payload={'campaign': row['id'], 'opened': opened},
            rows=[('campaigns', ident) for ident in opened],
        )
        notify_rows_written(conn, 'campaigns', opened)
    return opened


def _split(conn: sqlite3.Connection, row: dict, inv: str) -> dict:
    """La campagne d'un plan à plusieurs canaux garde le premier, et ouvre
    une sœur pour chacun des autres. Exemple : « email, linkedin » devient
    une campagne par e-mail, celle-ci, et une campagne sur LinkedIn."""
    channels = [c.strip() for c in str(row['channel']).split(',')]
    channels = [c for c in channels if c]
    if len(channels) < 2:
        return row
    conn.execute(
        'UPDATE campaigns SET channel=? WHERE id=?', (channels[0], row['id'])
    )
    row = campaign(conn, str(row['id'])) or row
    open_sisters(conn, row, channels[1:], inv)
    return row


def _number(settings: dict[str, str], name: str) -> int | None:
    value = str(settings.get(name, '')).strip()
    return int(value) if value.isdigit() else None


def _days(conn: sqlite3.Connection, venture: str, maximum: int) -> int:
    """La durée d'un test : celle du dernier plan validé du POC, au plus
    le maximum réglé."""
    row = conn.execute(
        'SELECT duration_days FROM product_plans WHERE venture_id=?'
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
    row = _split(conn, row, inv)
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
