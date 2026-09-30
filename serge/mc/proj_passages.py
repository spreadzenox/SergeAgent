#!/usr/bin/env python3
"""Les appels au modèle d'une invocation : la liste, et la fiche d'un appel.

Chaque appel est noté dans ``llm_usage`` : les tours d'outils, la réponse
finale, les appels ratés. Le coût est celui qu'OpenRouter a facturé, en
dollars, quand il le donne.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.mc.libelles import NIVEAUX

VERDICTS = {
    'ok': 'terminé',
    'format_invalide': 'format raté',
    'outil': 'tour d’outils',
    'erreur': 'appel raté',
}


def cout(cost_usd: Any) -> str:
    """Le coût d'un appel : « 0,0012 $ », ou « — » s'il n'est pas connu.

    Un coût non nul sous 0,0001 $ (un petit modèle) s'écrit « < 0,0001 $ »,
    jamais « 0,0000 $ » qui se lirait comme gratuit.
    """
    if cost_usd is None:
        return '—'
    if 0 < float(cost_usd) < 0.0001:
        return '< 0,0001 $'
    return f'{float(cost_usd):.4f} $'.replace('.', ',')


def passages(conn: sqlite3.Connection, ident: str) -> list[dict[str, Any]]:
    """Les 20 derniers appels au modèle d'une invocation."""
    lignes = []
    for rid, when, tin, tout, lat, verd, tier, model, cost in conn.execute(
        'SELECT id, created_at, tokens_in, tokens_out, latency_ms,'
        ' verdict, tier, model, cost_usd FROM llm_usage WHERE point=?'
        ' ORDER BY id DESC LIMIT 20',
        (ident,),
    ).fetchall():
        lignes.append(
            {
                'id': f'{ident}:{rid}',
                'type': 'llm_usage',
                'cellules': [
                    when or '—',
                    VERDICTS.get(str(verd), verd or '—'),
                    str(tier or '—'),
                    str(int(tin or 0) + int(tout or 0)),
                    cout(cost),
                    f'{int(lat or 0)} ms',
                    model or '—',
                ],
            }
        )
    return lignes


def project_llm_usage(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Un appel : ses jetons, son coût, sa durée."""
    point, sep, raw = ident.partition(':')
    if not sep or not raw.isdigit():
        return None
    row = conn.execute(
        'SELECT u.id, u.point, u.tier, u.model, u.tokens_in, u.tokens_out,'
        ' u.latency_ms, u.verdict, u.created_at, u.cost_usd,'
        " COALESCE(NULLIF(i.title, ''), u.point) FROM llm_usage u"
        ' LEFT JOIN invocations i ON i.id=u.point WHERE u.id=?',
        (int(raw),),
    ).fetchone()
    if row is None or str(row[1]) != point:
        return None
    titre = str(row[10])
    return {
        'type': 'llm_usage',
        'id': ident,
        'titre': f'{titre} · passage {raw}',
        'pourquoi': (
            'Un appel au modèle. Les jetons, la durée et le coût (donné par'
            ' OpenRouter, en dollars) sont sûrs.'
        ),
        'champs': [
            {'k': 'Invocation', 'v': titre},
            {'k': 'Quand', 'v': str(row[8] or '—')},
            {
                'k': 'Résultat',
                'v': VERDICTS.get(str(row[7]), str(row[7] or '—')),
            },
            {
                'k': 'Niveau de modèle',
                'v': NIVEAUX.get(str(row[2]), str(row[2] or '—')),
            },
            {'k': 'Nom du modèle', 'v': str(row[3] or '—')},
            {'k': 'Jetons lus', 'v': str(row[4] or 0)},
            {'k': 'Jetons écrits', 'v': str(row[5] or 0)},
            {'k': 'Coût', 'v': cout(row[9])},
            {'k': 'Durée', 'v': f'{int(row[6] or 0)} ms'},
        ],
        'enfants': [{'type': 'llm', 'id': point, 'titre': titre}],
        'preuve': '',
    }
