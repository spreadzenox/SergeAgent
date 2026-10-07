#!/usr/bin/env python3
"""Projecteurs P0 Live : urgents, feed, jauges (la file : proj_taches.py)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.funnels.contacts import address_value
from serge.llm.runtime import llm_spend
from serge.mc.proj_outils import apres_iso
from serge.tickets.lifecycle import OPENISH


def project_urgents(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Tickets urgents : GUICHET <15min, veto <1h, ALERT (P0 urgents).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {items: [{id, type, titre, expiry_at}]} (cap 20, expiries first).
    """
    _ = policy
    soon_15 = apres_iso(now, minutes=15)
    soon_60 = apres_iso(now, minutes=60)
    placeholders = ','.join('?' * len(OPENISH))
    rows = conn.execute(
        'SELECT id, type, title, expiry_at FROM tickets WHERE state IN'
        f' ({placeholders}) AND ((type=? AND expiry_at<>? AND expiry_at<?)'
        " OR (type=? AND expiry_at<>? AND expiry_at<?) OR type='ALERT')"
        " ORDER BY CASE WHEN expiry_at='' THEN 1 ELSE 0 END, expiry_at"
        ' LIMIT 20',
        (
            *sorted(OPENISH),
            'GUICHET',
            '',
            soon_15,
            'VETO_AMONT',
            '',
            soon_60,
        ),
    ).fetchall()
    return {
        'items': [
            {
                'id': row[0],
                'type': row[1],
                'titre': row[2],
                'expiry_at': row[3],
            }
            for row in rows
        ]
    }


def _feed_events(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT id, ts, type, actor, payload_json FROM events'
        ' ORDER BY id DESC LIMIT 30'
    ).fetchall():
        try:
            extra = json.loads(row[4] or '{}')
        except ValueError:
            extra = {}
        if not isinstance(extra, dict):
            extra = {}
        extra['event_id'] = str(row[0])
        items.append(
            {
                'ts': row[1],
                'source': 'event',
                'kind': row[2],
                'titre': '',
                'extra': extra,
            }
        )
    return items


def _feed_tickets(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT te.ts, te.kind, te.actor, t.id, t.title'
        ' FROM ticket_events te LEFT JOIN tickets t'
        ' ON t.id=te.ticket_id ORDER BY te.id DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[0],
                'source': 'ticket',
                'kind': row[1],
                'titre': str(row[4] or ''),
                'extra': {'ticket_id': row[3], 'actor': row[2]},
            }
        )
    return items


def _feed_touches(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    items = []
    for row in conn.execute(
        'SELECT t.id, t.created_at, t.channel, t.kind, t.status,'
        ' c.display, t.contact_id'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' ORDER BY t.created_at DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[1],
                'source': 'touche',
                'kind': f'{row[2]}.{row[4]}',
                'titre': str(
                    row[5]
                    or address_value(conn, str(row[6] or ''), 'email')
                    or address_value(conn, str(row[6] or ''), 'phone')
                    or row[6]
                    or ''
                ),
                'extra': {
                    'contact_kind': row[3],
                    'touch_id': str(row[0]),
                    'contact_id': str(row[6] or ''),
                },
            }
        )
    return items


def project_feed(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Feed unifié : events + tickets + touches, triés (P0 feed).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {items: [{ts, source, kind, titre, extra}] cap 30}.
        Calls voix : différés au lot 7 (ledger séparé).
    """
    _ = (policy, now)
    items = _feed_events(conn) + _feed_tickets(conn) + _feed_touches(conn)
    items.sort(key=lambda item: str(item['ts']), reverse=True)
    return {'items': items[:30]}


def _quota_jour(quotas: Mapping[str, Any], cle: str) -> int:
    try:
        return int(quotas.get(cle, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _touches_jour(conn: sqlite3.Connection, canal: str, jour: str) -> int:
    """Les envois partis ce jour-là, comptés comme le fait « Envoyer un
    message » pour son plafond du jour."""
    row = conn.execute(
        'SELECT COUNT(*) FROM touches WHERE channel=?'
        " AND status='sent' AND sent_at LIKE ?",
        (canal, f'{jour}%'),
    ).fetchone()
    return int(row[0] if row else 0)


def _barre(faits: int, quota: int) -> dict[str, Any]:
    return {
        'faits': faits,
        'quota': quota,
        'ratio': (faits / quota) if quota > 0 else None,
    }


def project_jauges(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Budgets : le coût des modèles du jour et du mois, et les quotas
    quotidiens de la Policy.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (budget + quotas).
        now: Maintenant ISO UTC.

    Returns:
        Dict llm / mois / email / voix / linkedin (ratio None si plafond 0).
    """
    day = now[:10]
    depense = llm_spend(conn, policy, day)
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    eur = depense.eur
    # Ce que Serge nous coûte en IA ce mois-ci (décision Q68).
    mois = llm_spend(conn, policy, day[:7]).eur
    cap_mois = float(budget.get('monthly_eur', 0) or 0)
    quotas = policy.get('quotas') or {}
    email = _barre(
        _touches_jour(conn, 'email', day),
        _quota_jour(
            (policy.get('channels') or {}).get('email') or {}, 'max_per_day'
        ),
    )
    return {
        'llm': {
            'tokens_jour': depense.tokens,
            # Coût réel donné par OpenRouter ; les jetons des appels dont le
            # coût n'est pas connu sont comptés à part, jamais estimés.
            'eur': round(eur, 4),
            'jetons_sans_cout': depense.unknown_tokens,
            'plafond_eur': cap,
            'ratio': (eur / cap) if cap > 0 else None,
            'libelle': 'Modèles, aujourd’hui',
        },
        'mois': {
            'eur': round(mois, 4),
            'plafond_eur': cap_mois,
            'ratio': (mois / cap_mois) if cap_mois > 0 else None,
            'libelle': 'Ce que Serge coûte ce mois-ci',
        },
        'email': {
            **email,
            'envoyes': email['faits'],
            'libelle': 'E-mails',
        },
        'voix': {
            **_barre(
                _touches_jour(conn, 'voice', day),
                _quota_jour(quotas, 'voice_max_calls_per_day'),
            ),
            'libelle': 'Appels',
        },
        'linkedin': {
            **_barre(
                _touches_jour(conn, 'linkedin', day),
                _quota_jour(quotas, 'linkedin_connect_per_day'),
            ),
            'libelle': 'Invitations LinkedIn',
        },
    }
