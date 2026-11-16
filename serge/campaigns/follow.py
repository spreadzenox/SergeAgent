#!/usr/bin/env python3
"""Suivre une campagne en cours : la clore, lui chercher des prospects, ou
attendre.

Une campagne se termine, au plus tôt (décision Q92), quand :

1. elle a son compte de prospects (ou n'en trouve plus), plus aucun
   message n'attend de partir, et rien n'est parti depuis
   ``jours_sans_envoi`` jours (8 : un jour de plus que le plus long délai
   entre deux relances, donc toutes les relances sont faites) ;
2. ou, pour un test léger, elle a atteint sa fin prévue (la durée du
   plan).

Sinon, on lui cherche des prospects s'il lui en manque (au total, et
cette semaine pour une campagne lourde) et que Serge a moins de
``jours_d_avance`` jours d'envois d'avance. Une recherche qui n'a ajouté
aucun prospect est comptée ; après ``recherches_vides_max`` de suite, la
campagne n'en cherche plus.

Exemple : 40 artisans contactés en 4 jours, deux relances, la dernière au
14e jour ; la campagne se termine au 22e jour.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from typing import Any

from serge.campaigns.start import FULL, SMOKE, campaign
from serge.db.store import utcnow
from serge.interpreter.settings import load_settings
from serge.policy_store import setting_value

# Un envoi qui n'est pas encore parti.
WAITING = ('to_write', 'pending', 'sending', 'waiting_owner')
OVER = ('FINISHED', 'CANCELLED')


def found(conn: sqlite3.Connection, campaign_id: str, since: str = '') -> int:
    """Les prospects d'une campagne : ceux qui y ont un premier message."""
    return int(
        conn.execute(
            'SELECT COUNT(DISTINCT contact_id) FROM touches'
            " WHERE campaign_id=? AND kind='first' AND created_at>=?",
            (campaign_id, since),
        ).fetchone()[0]
    )


def _activity(conn: sqlite3.Connection, row: dict) -> tuple[int, str]:
    """Les envois qui attendent encore, et l'heure du dernier parti, parmi
    les premiers messages de la campagne et leurs relances."""
    holes = ','.join('?' * len(WAITING))
    waiting, last = conn.execute(
        f'SELECT COALESCE(SUM(status IN ({holes})), 0),'
        " COALESCE(MAX(CASE WHEN status='sent' THEN sent_at END), '')"
        " FROM touches WHERE channel=? AND kind IN ('first', 'followup')"
        ' AND contact_id IN (SELECT contact_id FROM touches'
        " WHERE campaign_id=? AND kind='first')",
        (*WAITING, row['channel'], row['id']),
    ).fetchone()
    return int(waiting), str(last)


def _searching(conn: sqlite3.Connection, campaign_id: str, inv: str) -> bool:
    """Une recherche de prospects attend-elle ou tourne-t-elle déjà pour
    cette campagne (une autre tâche que celles de cette invocation) ?"""
    return (
        conn.execute(
            'SELECT 1 FROM tasks t JOIN task_params p ON p.task_id=t.id'
            " WHERE p.name='campaign_id' AND p.value=?"
            " AND t.status IN ('ready', 'running') AND t.invocation_id<>?",
            (campaign_id, inv),
        ).fetchone()
        is not None
    )


def _count_search(conn: sqlite3.Connection, row: dict, have: int) -> int:
    """Note une recherche qui part ; rend les recherches vides de suite."""
    empty = int(row['dry_searches'])
    if int(row['found_at_search']) >= 0:
        empty = empty + 1 if have == int(row['found_at_search']) else 0
    conn.execute(
        'UPDATE campaigns SET dry_searches=?, found_at_search=? WHERE id=?',
        (empty, have, row['id']),
    )
    return empty


def _test_over(conn: sqlite3.Connection, row: dict) -> str:
    """« oui » si, cette campagne close, tout le test du business est fini."""
    if row['phase'] != SMOKE:
        return ''
    holes = ','.join('?' * len(OVER))
    others = conn.execute(
        'SELECT COUNT(*) FROM campaigns WHERE venture_id=? AND phase=?'
        f' AND id<>? AND state NOT IN ({holes})',
        (row['venture_id'], SMOKE, row['id'], *OVER),
    ).fetchone()[0]
    return '' if int(others) else 'oui'


def follow_campaign(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Suivre une campagne » : ``{campaign_id}``.

    Rend ``action`` : ``clore`` (avec ``state`` = ``FINISHED``, la raison,
    et ``test_fini`` = « oui » quand c'était la dernière campagne de test
    du business), ``chercher`` (il lui faut des prospects) ou ``attendre``.
    """
    row = campaign(conn, str(args.get('campaign_id') or ''))
    if row is None or row['state'] != 'RUNNING':
        return {'ok': True, 'action': 'attendre', 'raison': 'pas en cours'}
    base = {
        'ok': True,
        'campaign_id': row['id'],
        'venture_id': row['venture_id'],
    }
    settings = load_settings(conn, inv)
    now = datetime.fromisoformat(utcnow())
    have = found(conn, str(row['id']))
    waiting, last = _activity(conn, row)
    dry = int(row['dry_searches']) >= int(
        settings.get('recherches_vides_max') or 3
    )
    quiet = timedelta(days=float(settings.get('jours_sans_envoi') or 0))
    raison = ''
    if (
        row['phase'] == SMOKE
        and row['planned_end_at']
        and now >= datetime.fromisoformat(str(row['planned_end_at']))
    ):
        raison = 'la durée du test est atteinte'
    elif (
        (have >= int(row['n_target']) or dry)
        and not waiting
        and (not last or now - datetime.fromisoformat(last) >= quiet)
    ):
        raison = (
            'tous ses prospects sont contactés et relancés'
            if have >= int(row['n_target'])
            else 'plus de prospects à contacter'
        )
    if raison:
        return {
            **base,
            'action': 'clore',
            'state': 'FINISHED',
            'raison': raison,
            'test_fini': _test_over(conn, row),
        }
    week = (now - timedelta(days=7)).isoformat()
    short = have < int(row['n_target']) and (
        row['phase'] != FULL
        or found(conn, str(row['id']), week) < int(row['n_week'])
    )
    cap = setting_value(conn, f'channels.{row["channel"]}.max_per_day')
    ahead = float(settings.get('jours_d_avance') or 1) * float(cap or 0)
    if (
        not short
        or dry
        or (cap is not None and waiting >= ahead)
        or _searching(conn, str(row['id']), inv)
    ):
        return {**base, 'action': 'attendre', 'raison': ''}
    if _count_search(conn, row, have) >= int(
        settings.get('recherches_vides_max') or 3
    ):
        return {**base, 'action': 'attendre', 'raison': 'recherches vides'}
    return {**base, 'action': 'chercher', 'raison': ''}
