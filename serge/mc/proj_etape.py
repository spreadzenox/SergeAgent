#!/usr/bin/env python3
"""Étapes du pipe : textes, ordre des jugements, fiche MC."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.etape_fiches import fiche_etape, precedente
from serge.etapes import ETAPE_IDS
from serge.mc.libelles import titre_llm
from serge.mc.llm_roles import role_de

# Ordre d’exécution réel (pas l’ordre du YAML). Le reste = « à part ».
ORDRE: dict[str, list[str]] = {
    'pre_prospection': [
        'listen_discover_needs_a',
        'listen_discover_needs_b',
        'listen_choose_poc',
    ],
    'conception_poc': ['draft_hypothesis_smoke'],
    'prospection_light': [
        'fill_slots',
        'score_lead_departage',
    ],
    'choix_venture': [
        'resume_test',
        'draft_hypothesis_full',
        'options_pivot',
    ],
    'build_venture': [
        'build_artifact',
        'review_build',
        'summarize_build_debt',
    ],
    'prospection_lourde': [
        'plan_scale',
        'classify_reply',
        'review_other',
        'extract_meeting',
        'reply_intent',
        'write_followup',
        'summarize_thread',
        'render_context_fr',
        'voice_script',
        'voice_dialog',
        'score_call',
        'judge_allocator',
    ],
    'collect_feedback': ['consolidate'],
    'caisse': [],
}

RESTE: dict[str, list[str]] = {}


def _court(nom: str) -> str:
    role = role_de(nom)[0]
    tete, sep, _ = role.partition('.')
    return (tete + '.') if sep else role


def lister_jugements(
    conn: sqlite3.Connection, etape: str, chauds: set[str] | None = None
) -> list[dict[str, Any]]:
    """Jugements d’une étape : d’abord l’ordre, puis le reste à part.

    Args:
        conn: Canon (``llm_points``).
        etape: Id d’étape.
        chauds: Points vus récemment (badge).

    Returns:
        Lignes `{id, titre, detail, rang, ordre, chaud}`.
    """
    chauds = chauds or set()
    rows = conn.execute(
        'SELECT id, titre FROM llm_points WHERE etape_id=?',
        (etape,),
    ).fetchall()
    titres = {str(r[0]): str(r[1] or '') for r in rows}
    connus = list(titres)
    suite = [n for n in ORDRE.get(etape, []) if n in titres]
    reste = [n for n in RESTE.get(etape, []) if n in titres and n not in suite]
    reste.extend(n for n in connus if n not in suite and n not in reste)
    lignes = []
    for i, nom in enumerate(suite, 1):
        lignes.append(
            {
                'id': nom,
                'titre': titres[nom] or titre_llm(nom),
                'detail': _court(nom),
                'rang': i,
                'ordre': True,
                'chaud': nom in chauds,
            }
        )
    for nom in reste:
        lignes.append(
            {
                'id': nom,
                'titre': titres[nom] or titre_llm(nom),
                'detail': _court(nom),
                'rang': 0,
                'ordre': False,
                'chaud': nom in chauds,
            }
        )
    return lignes


def project_etape(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Fiche d’une étape du pipe : rôle, dépendance, jugements cliquables.

    Args:
        conn: Canon (lecture des points chauds).
        ident: Id d’étape.

    Returns:
        Payload fiche MC, ou None si l’étape est inconnue.
    """
    if ident not in ETAPE_IDS:
        return None
    spec = fiche_etape(conn, ident)
    if spec is None:
        return None
    chauds = {
        str(r[0])
        for r in conn.execute(
            'SELECT DISTINCT point FROM llm_usage ORDER BY id DESC LIMIT 20'
        ).fetchall()
    }
    jugs = lister_jugements(conn, ident, chauds)
    prec = precedente(conn, ident)
    prec_fiche = fiche_etape(conn, prec) if prec else None
    titre_prec = (prec_fiche or {}).get('titre') or ''
    liens_ord = [
        {
            'type': 'llm',
            'id': j['id'],
            'titre': f'{j["rang"]}. {j["titre"]}'
            if j['ordre']
            else j['titre'],
        }
        for j in jugs
        if j['ordre']
    ]
    liens_reste = [
        {'type': 'llm', 'id': j['id'], 'titre': j['titre']}
        for j in jugs
        if not j['ordre']
    ]
    extra = []
    from serge.catalogue import objets_de_etape

    bundle = objets_de_etape(conn, ident)
    tech_liens = [
        {'type': 'tech', 'id': t['id'], 'titre': t['titre']}
        for t in bundle['tech']
    ]
    if ident == 'pre_prospection':
        extra.append(
            {
                'type': 'ecoute',
                'id': 'pages',
                'titre': 'Pages vraiment lues (miroir)',
            }
        )
    cadres = [
        {'titre': 'À quoi ça sert', 'texte': spec['pourquoi']},
        {
            'titre': 'Pourquoi ça dépend de avant',
            'texte': spec['dependance'],
            'liens': (
                [
                    {
                        'type': 'etape',
                        'id': prec,
                        'titre': f'Étape d’avant : {titre_prec}',
                    }
                ]
                if prec
                else []
            ),
        },
        {'titre': 'Comment c’est fait vraiment', 'texte': spec['comment']},
        {
            'titre': 'Jugements, dans l’ordre',
            'texte': (
                'Chaque ligne ouvre la page du jugement.'
                if liens_ord
                else 'Pas de jugement LLM ici — surtout des règles et Stripe.'
            ),
            'liens': liens_ord,
        },
    ]
    if liens_reste:
        cadres.append(
            {
                'titre': 'Autres jugements (pas d’ordre fixe)',
                'liens': liens_reste,
            }
        )
    if extra:
        cadres.append({'titre': 'Voir aussi', 'liens': extra})
    if tech_liens:
        cadres.append(
            {
                'titre': 'Invocations techniques',
                'texte': 'Déterministes, rattachées à ce sac.',
                'liens': tech_liens,
            }
        )
    canal_liens = [
        {'type': 'canal', 'id': c['id'], 'titre': c['titre']}
        for c in bundle['canaux']
    ]
    if canal_liens:
        cadres.append(
            {
                'titre': 'Canaux',
                'texte': 'Moyens d’écrire vers l’extérieur depuis ce sac.',
                'liens': canal_liens,
            }
        )
    return {
        'type': 'etape',
        'id': ident,
        'titre': spec['titre'],
        'pourquoi': spec['pourquoi'],
        'champs': [
            {'k': 'Invocations LLM', 'v': str(len(jugs))},
            {'k': 'Invocations techniques', 'v': str(len(tech_liens))},
            {'k': 'Canaux', 'v': str(len(canal_liens))},
            {'k': 'Étape d’avant', 'v': titre_prec or '— (début)'},
            {'k': 'Dernière modification', 'v': spec['updated_at'] or '—'},
        ],
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
