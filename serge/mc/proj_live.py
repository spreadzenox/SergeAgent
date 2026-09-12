#!/usr/bin/env python3
"""Projecteurs P0 Live : hero, urgents, file, feed, jauges (purs, testés)."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.llm.runtime import daily_tokens
from serge.mc.proj_outils import apres_iso
from serge.scheduler import next_ready
from serge.tickets.lifecycle import OPENISH


def project_hero(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """Ce qui se passe : RUNNING actuel + file READY (P0 hero).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO (ignoré, uniformité).

    Returns:
        Dict {running, ready, next}.
    """
    _ = policy
    row = conn.execute(
        'SELECT id, kind, venture_id, created_at FROM work_items'
        " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    running = None
    if row is not None:
        running = {
            'id': row[0],
            'kind': row[1],
            'venture_id': row[2],
            'since': row[3],
        }
    ready = conn.execute(
        "SELECT COUNT(*) FROM work_items WHERE status='READY'"
    ).fetchone()[0]
    nxt = next_ready(conn, now)
    following = None
    if nxt is not None:
        following = {
            'id': nxt['id'],
            'kind': nxt['kind'],
            'venture_id': nxt['venture_id'],
        }
    return {'running': running, 'ready': int(ready), 'next': following}


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


def project_file(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """File d'exécution : RUNNING + READY + prochain (P0 file).

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (ignorée, uniformité).
        now: Maintenant ISO UTC.

    Returns:
        Dict {running: [...cap 10], ready_count: int, next: {...} | None}.
    """
    _ = policy
    running = [
        {
            'id': row[0],
            'kind': row[1],
            'venture_id': row[2],
            'since': row[3],
        }
        for row in conn.execute(
            'SELECT id, kind, venture_id, created_at FROM work_items'
            " WHERE status='RUNNING' ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
    ]
    ready_count = conn.execute(
        "SELECT COUNT(*) FROM work_items WHERE status='READY'"
    ).fetchone()[0]
    nxt = next_ready(conn, now)
    following = None
    if nxt is not None:
        following = {
            'id': nxt['id'],
            'kind': nxt['kind'],
            'venture_id': nxt['venture_id'],
        }
    return {
        'running': running,
        'ready_count': int(ready_count),
        'next': following,
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
        ' COALESCE(c.display, c.email, t.contact_id), t.contact_id'
        ' FROM touches t LEFT JOIN contacts c ON c.id=t.contact_id'
        ' ORDER BY t.created_at DESC LIMIT 30'
    ).fetchall():
        items.append(
            {
                'ts': row[1],
                'source': 'touche',
                'kind': f'{row[2]}.{row[4]}',
                'titre': str(row[5] or ''),
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
    row = conn.execute(
        'SELECT COUNT(*) FROM touches WHERE channel=?'
        " AND status='sent' AND created_at LIKE ?",
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
    """Budgets du jour : LLM € + quotas quotidiens de la Policy.

    Args:
        conn: Connexion canon (lecture).
        policy: Policy (budget + quotas).
        now: Maintenant ISO UTC.

    Returns:
        Dict llm / email / voix / linkedin (ratio None si plafond 0).
    """
    day = now[:10]
    spent_in, spent_out = daily_tokens(conn, day)
    tokens = spent_in + spent_out
    budget = policy.get('budget') or {}
    cap = float(budget.get('llm_daily_eur', 0) or 0)
    rate = float(budget.get('llm_eur_per_1k_tokens', 0) or 0)
    eur = tokens / 1000 * rate
    quotas = policy.get('quotas') or {}
    email = _barre(
        _touches_jour(conn, 'email', day),
        _quota_jour(quotas, 'email_per_mailbox_per_day'),
    )
    return {
        'llm': {
            'tokens_jour': tokens,
            'eur_estimes': round(eur, 4),
            'plafond_eur': cap,
            'ratio': (eur / cap) if cap > 0 else None,
            'libelle': 'Jugements (plafond € du jour)',
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


def project_file_detail(conn: sqlite3.Connection, now: str) -> dict[str, Any]:
    """File complète : en cours puis prêts (priorité, FIFO), y compris en pause."""
    from serge.mc.libelles import CANAUX, ETATS_WORK, verbe

    nxt = next_ready(conn, now)
    prochain_id = str(nxt['id']) if nxt else ''
    rows = conn.execute(
        'SELECT w.id, w.kind, w.status, w.priority, w.blocked_until,'
        ' w.created_at, w.attempts, w.campaign_id, w.contact_id,'
        ' v.name, c.display, camp.channel FROM work_items w'
        ' LEFT JOIN ventures v ON v.id=w.venture_id'
        ' LEFT JOIN contacts c ON c.id=w.contact_id'
        ' LEFT JOIN campaigns camp ON camp.id=w.campaign_id'
        " WHERE w.status IN ('READY','RUNNING')"
        " ORDER BY CASE w.status WHEN 'RUNNING' THEN 0 ELSE 1 END,"
        ' w.priority DESC, w.created_at ASC'
    ).fetchall()
    lignes = []
    enfants = []
    for i, row in enumerate(rows, start=1):
        ident, kind, statut, prio, pause, created, essais = row[:7]
        campagne, contact, nom, qui, canal = row[7:]
        etat = ETATS_WORK.get(statut, statut)
        if ident == prochain_id:
            etat = 'Prochain'
        elif statut == 'READY' and pause and pause > now:
            etat = 'En pause'
        titre = verbe(str(kind))
        canal_fr = CANAUX.get(canal, canal) if canal else '—'
        lignes.append(
            {
                'id': ident,
                'type': 'work_item',
                'cellules': [
                    str(i),
                    titre,
                    etat,
                    str(prio),
                    nom or '—',
                    canal_fr if campagne else '—',
                    qui or '—',
                    pause if pause and pause > now else '—',
                    created or '—',
                    str(essais),
                ],
            }
        )
        enfants.append(
            {'type': 'work_item', 'id': ident, 'titre': f'{i}. {titre}'}
        )
    return {
        'type': 'file',
        'id': 'canon',
        'titre': 'File d’exécution',
        'pourquoi': (
            'Ordre réel de l’ordonnanceur : d’abord ce qui tourne,'
            ' puis les prêts par priorité, le plus ancien d’abord.'
        ),
        'champs': [
            {'k': 'Prêts', 'v': str(sum(1 for r in rows if r[2] == 'READY'))},
            {
                'k': 'En cours',
                'v': str(sum(1 for r in rows if r[2] == 'RUNNING')),
            },
            {
                'k': 'Prochain',
                'v': verbe(str(nxt['kind'])) if nxt else '—',
            },
        ],
        'tableau': {
            'colonnes': [
                'Rang',
                'Travail',
                'État',
                'Priorité',
                'Venture',
                'Campagne',
                'Contact',
                'Pause',
                'Depuis',
                'Essais',
            ],
            'lignes': lignes,
        },
        'enfants': enfants,
        'preuve': '',
    }
