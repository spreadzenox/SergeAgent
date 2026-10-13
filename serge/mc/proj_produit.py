#!/usr/bin/env python3
"""Ce que la fiche d'un business montre de son produit (lot 10, Q91).

Son dernier plan (POC ou produit fini) et les remarques du critique, les
demandes de ses clients et ce que le plan en a fait, ses passages de
construction avec le verdict du relecteur, les captures du relecteur, ses
publications (staging et prod : la version, l'adresse,
l'état, et pourquoi la dernière a raté) et ses versions figées.
"""

from __future__ import annotations

import sqlite3
from typing import Any

CIBLES = {'staging': 'Staging', 'prod': 'Prod'}
PLANS = {
    'draft': 'proposé',
    'challenged': 'critiqué',
    'validated': 'validé',
    'to_fix': 'à corriger',
    'refused': 'refusé',
}
PASSAGES = {'built': 'construit', 'unfinished': 'pas fini', 'reviewed': 'relu'}
VERDICTS = {'bon': 'bon', 'a_corriger': 'à corriger'}
ETATS = {'running': 'en ligne', 'failed': 'ratée', 'stopped': 'arrêtée'}
DEMANDES = {
    'new': 'nouvelle',
    'kept': 'retenue',
    'refused': 'refusée',
    'delivered': 'livrée',
}


def cadres_produit(
    conn: sqlite3.Connection, venture_id: str
) -> list[dict[str, Any]]:
    """Les cadres du produit d'un business, ceux qui ont quelque chose."""
    cadres = (
        _plan(conn, venture_id)
        + _demandes(conn, venture_id)
        + _passages(conn, venture_id)
    )
    publications = conn.execute(
        'SELECT target, version, hostname, status, last_error, updated_at'
        ' FROM deployments WHERE venture_id=? ORDER BY target DESC',
        (venture_id,),
    ).fetchall()
    if publications:
        cadres.append(
            {
                'titre': 'En ligne',
                'champs': [
                    {
                        'k': f'{CIBLES.get(p[0], p[0])} (v{p[1]})',
                        'v': f'https://{p[2]} — {ETATS.get(p[3], p[3])}'
                        + (f' : {p[4]}' if p[4] else '')
                        + f' ({str(p[5])[:16]})',
                    }
                    for p in publications
                ],
            }
        )
    versions = conn.execute(
        'SELECT deliverable, version, path_or_url, size_bytes, created_at'
        " FROM artifacts WHERE venture_id=? AND kind='version'"
        ' ORDER BY created_at DESC LIMIT 20',
        (venture_id,),
    ).fetchall()
    if versions:
        cadres.append(
            {
                'titre': 'Versions',
                'champs': [
                    {
                        'k': f'{v[0]} v{v[1]}',
                        'v': f'{v[2]} ({int(v[3]) // 1024} Ko,'
                        f' {str(v[4])[:16]})',
                    }
                    for v in versions
                ],
            }
        )
    return cadres


def _plan(conn: sqlite3.Connection, venture_id: str) -> list[dict[str, Any]]:
    """Le dernier plan et les remarques du critique sur ce plan."""
    plan = conn.execute(
        'SELECT id, kind, round, status, hypothesis, deliverable, price,'
        ' channel, prospects, plan, scenarios, challenge, owner_notes,'
        ' domain FROM product_plans WHERE venture_id=?'
        ' ORDER BY created_at DESC, rowid DESC LIMIT 1',
        (venture_id,),
    ).fetchone()
    if plan is None:
        return []
    champs = [
        ('Pour', 'le POC' if plan[1] == 'poc' else 'le produit fini'),
        ('Tour de critique', str(plan[2])),
        ('État', PLANS.get(str(plan[3]), str(plan[3]))),
        ('Hypothèse', plan[4]),
        ('Ce qu’on peut essayer', plan[5]),
        ('Prix', plan[6]),
        (
            ('Domaine', plan[13] or '—')
            if plan[1] == 'product'
            else ('Test', f'{plan[8]} prospects par {plan[7]}')
        ),
        ('Avis du critique', plan[11] or '—'),
    ]
    if plan[12]:
        champs.append(('Consignes d’un humain', plan[12]))
    cadres: list[dict[str, Any]] = [
        {
            'titre': 'Le plan',
            'champs': [{'k': k, 'v': str(v)} for k, v in champs],
            'pre': f'{plan[9]}\n\nScénarios de test :\n{plan[10]}',
        }
    ]
    remarques = conn.execute(
        'SELECT round, text FROM plan_critiques WHERE plan_id=?'
        ' ORDER BY created_at',
        (plan[0],),
    ).fetchall()
    if remarques:
        cadres.append(
            {
                'titre': 'Les remarques du critique',
                'champs': [
                    {'k': f'Tour {r[0]}', 'v': str(r[1])} for r in remarques
                ],
            }
        )
    return cadres


def _demandes(
    conn: sqlite3.Connection, venture_id: str
) -> list[dict[str, Any]]:
    """Les demandes des clients et ce que le plan du produit en a fait."""
    demandes = conn.execute(
        'SELECT kind, text, status, reason, delivered_version'
        ' FROM customer_requests WHERE venture_id=?'
        ' ORDER BY created_at DESC LIMIT 30',
        (venture_id,),
    ).fetchall()
    if not demandes:
        return []
    return [
        {
            'titre': 'Les demandes des clients',
            'champs': [
                {
                    'k': f'{d[0]} — {DEMANDES.get(str(d[2]), d[2])}'
                    + (f' en v{d[4]}' if d[4] else ''),
                    'v': str(d[1]) + (f' (raison : {d[3]})' if d[3] else ''),
                }
                for d in demandes
            ],
        }
    ]


def _passages(
    conn: sqlite3.Connection, venture_id: str
) -> list[dict[str, Any]]:
    """Les derniers passages de construction, et les captures du relecteur."""
    passages = conn.execute(
        'SELECT deliverable, pass, status, verdict, remarks, report'
        ' FROM builds WHERE venture_id=?'
        ' ORDER BY created_at DESC, rowid DESC LIMIT 6',
        (venture_id,),
    ).fetchall()
    cadres: list[dict[str, Any]] = []
    if passages:
        cadres.append(
            {
                'titre': 'Les passages de construction',
                'champs': [
                    {
                        'k': f'{p[0]}, passage {p[1]}'
                        f' — {PASSAGES.get(str(p[2]), p[2])}'
                        + (
                            f', {VERDICTS.get(str(p[3]), p[3])}'
                            if p[3]
                            else ''
                        ),
                        'v': str(p[4] or p[5])[:1500],
                    }
                    for p in passages
                ],
            }
        )
    captures = conn.execute(
        "SELECT id FROM artifacts WHERE venture_id=? AND kind='capture'"
        ' ORDER BY created_at DESC LIMIT 12',
        (venture_id,),
    ).fetchall()
    if captures:
        cadres.append(
            {
                'titre': 'Les dernières captures',
                'images': [
                    {
                        'src': f'/owner/api/fichier?id={c[0]}',
                        'legende': f'Capture {n}',
                    }
                    for n, c in enumerate(reversed(captures), 1)
                ],
            }
        )
    return cadres


def boutons_du_business(
    conn: sqlite3.Connection, venture_id: str
) -> list[dict[str, Any]]:
    """Les boutons déclarés en base dont le formulaire attend un business.

    Ils s'affichent sur la fiche de chaque business, son numéro déjà
    rempli. Exemple : « Supprimer de Stripe (mode test) ».
    """
    return [
        {
            'libelle': str(titre),
            'route': '/owner/api/bouton',
            'charge': {
                'trigger_id': str(ident),
                'form': {'venture_id': venture_id},
            },
            'confirmer': str(confirmer or ''),
        }
        for ident, titre, confirmer in conn.execute(
            'SELECT t.id, t.title, t.confirm_text FROM triggers t'
            ' JOIN invocations i ON i.id=t.invocation_id'
            " WHERE t.event='button' AND t.enabled=1 AND t.deleted_at=''"
            " AND i.enabled=1 AND i.deleted_at=''"
            ' AND t.id IN (SELECT trigger_id FROM trigger_params'
            " WHERE source='form' AND value='venture_id') ORDER BY t.id"
        ).fetchall()
    ]
