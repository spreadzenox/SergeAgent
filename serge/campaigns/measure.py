#!/usr/bin/env python3
"""Mesurer un test léger fini, et le juger.

Le compte rendu : les prospects contactés par canal (leur premier message
est parti), ceux qui ont répondu, les réactions, les points (grille du
lot 9), la dépense et les points par euro. Puis le verdict, avec des
seuils en chiffres absolus (décision Q93), réglages de l'invocation :
``prospects_min`` (30), ``points_min`` (10) et ``points_par_euro_min`` (0).
Le code juge, pas un modèle.

Exemple de raison : « 4 points, moins que les 10 demandés ».
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.campaigns.start import SMOKE
from serge.funnels.depense import depense_business, points_par_euro, texte_euros
from serge.funnels.points import points_prospects, texte_points
from serge.interpreter.settings import load_settings


def _contacted(conn: sqlite3.Connection, venture: str) -> dict[str, int]:
    """Les prospects contactés pendant le test, par canal."""
    return {
        str(channel): int(count)
        for channel, count in conn.execute(
            'SELECT t.channel, COUNT(DISTINCT t.contact_id) FROM touches t'
            ' JOIN campaigns c ON c.id=t.campaign_id'
            " WHERE c.venture_id=? AND c.phase=? AND t.kind='first'"
            " AND t.status='sent' GROUP BY t.channel ORDER BY t.channel",
            (venture, SMOKE),
        ).fetchall()
    }


def _verdict(
    settings: dict[str, str],
    contacted: int,
    points: float,
    per_euro: float | None,
) -> tuple[str, str]:
    """``(retenu ou non_retenu, la raison)``."""
    checks = (
        ('prospects_min', contacted, 'prospect(s) contacté(s)'),
        ('points_min', points, 'point(s)'),
        ('points_par_euro_min', per_euro, 'point(s) par euro'),
    )
    for name, value, label in checks:
        wanted = float(settings.get(name) or 0)
        # Sans dépense, pas de points par euro : ce seuil ne refuse rien.
        if value is not None and float(value) < wanted:
            return (
                'non_retenu',
                f'{texte_points(float(value))} {label}, moins que les'
                f' {texte_points(wanted)} demandés',
            )
    return 'retenu', 'le test passe les seuils'


def measure_test(
    conn: sqlite3.Connection, _tool: str, args: dict[str, Any], inv: str
) -> dict[str, Any]:
    """Capacité « Mesurer un test » : ``{venture_id}``.

    Rend le compte rendu, que les règles d'écriture rangent dans
    ``test_reports`` : ``contacted``, ``replies``, ``points``,
    ``spend_eur``, ``points_per_eur``, ``figures`` (le détail, en clair),
    ``verdict`` et ``verdict_reason``.
    """
    venture = str(args.get('venture_id') or '')
    by_channel = _contacted(conn, venture)
    best = points_prospects(conn, venture)
    points = round(sum(v['points'] for v in best.values()), 1)
    spend = float(depense_business(conn, venture)['total_eur'])
    per_euro = points_par_euro(points, spend)
    contacted = sum(by_channel.values())
    reactions: dict[str, int] = {}
    for found in best.values():
        reactions[found['reaction']] = reactions.get(found['reaction'], 0) + 1
    lines = [
        *(f'{channel} : {count} contacté(s)' for channel, count in by_channel.items()),
        'Réactions : '
        + (
            ', '.join(f'{n} « {r} »' for r, n in sorted(reactions.items()))
            or 'aucune'
        ),
        f'Points : {texte_points(points)}',
        f'Dépense : {texte_euros(spend)} €',
        'Points par euro : '
        + ('—' if per_euro is None else texte_points(per_euro)),
    ]
    verdict, raison = _verdict(
        load_settings(conn, inv), contacted, points, per_euro
    )
    return {
        'ok': True,
        'venture_id': venture,
        'contacted': contacted,
        'replies': len(best),
        'points': points,
        'spend_eur': round(spend, 4),
        'points_per_eur': per_euro,
        'figures': '\n'.join(lines),
        'verdict': verdict,
        'verdict_reason': raison,
    }
