#!/usr/bin/env python3
"""Étapes du pipe : textes, ordre des jugements, fiche MC."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.mc.libelles import LLM_ETAPE, titre_llm
from serge.mc.llm_roles import role_de

# Ordre d’exécution réel (pas l’ordre du YAML). Le reste = « à part ».
ORDRE: dict[str, list[str]] = {
    'pre_prospection': ['cluster_demand'],
    'conception_poc': ['draft_hypothesis_smoke'],
    'prospection_light': [
        'qualify_prospect',
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
        'draft_price',
        'judge_allocator',
    ],
    'collect_feedback': ['consolidate', 'edit_serge_md'],
    'caisse': [],
}

PRECEDENTE = {
    'pre_prospection': None,
    'conception_poc': 'pre_prospection',
    'prospection_light': 'conception_poc',
    'choix_venture': 'prospection_light',
    'build_venture': 'choix_venture',
    'prospection_lourde': 'build_venture',
    'collect_feedback': 'prospection_lourde',
    'caisse': 'prospection_lourde',
}

ETAPES: dict[str, dict[str, str]] = {
    'pre_prospection': {
        'titre': 'Pré-prospection',
        'pourquoi': (
            'Serge lit ce que des inconnus ont déjà écrit (forums, flux…).'
            ' But : sentir une demande réelle, pas inventer une idée.'
        ),
        'dependance': 'Rien avant. C’est le début du pipe.',
        'comment': (
            'Ramasser des pages, les ranger, puis une invocation LLM les'
            ' met en paquets. Le navigateur n’est pas encore un bouton.'
        ),
    },
    'conception_poc': {
        'titre': 'Conception d’un PoC',
        'pourquoi': (
            'On écrit la pré-venture : produit, specs, prérequis, puis on'
            ' appelle le builder si un livrable est nécessaire.'
        ),
        'dependance': (
            'Sans paquets de demandes (pré-prospection), on n’a qu’une intuition.'
        ),
        'comment': (
            'Le PoC (landing, SaaS, livrable) sert ensuite au smoke test :'
            ' on ne vend plus seulement un concept.'
        ),
    },
    'prospection_light': {
        'titre': 'Prospection light',
        'pourquoi': (
            'Smoke test multicanal (N configurable dans Mission Control),'
            ' avec le PoC s’il existe.'
        ),
        'dependance': 'Sans pré-venture écrite, on ne saurait pas ce qu’on mesure.',
        'comment': (
            'Mêmes canaux que la prospection lourde (e-mail, appel). On coupe'
            ' ce sac, pas le kind : la lourde peut continuer à envoyer.'
        ),
    },
    'choix_venture': {
        'titre': 'Choix de venture',
        'pourquoi': (
            'Parmi les N pré-ventures et leurs smokes, garder la plus prometteuse.'
        ),
        'dependance': 'Sans résultats de smoke, le choix n’est qu’une préférence.',
        'comment': (
            'Aujourd’hui N=1 actif max. Mission Control pourra ouvrir la porte.'
        ),
    },
    'build_venture': {
        'titre': 'Build / rebuild',
        'pourquoi': (
            'Créer ou améliorer la venture active : livrable, delivery,'
            ' onboarding client.'
        ),
        'dependance': 'On build à partir de la pré-venture choisie et des retours.',
        'comment': (
            'Toute la partie building / delivery est ici, y compris après vente.'
        ),
    },
    'prospection_lourde': {
        'titre': 'Prospection lourde',
        'pourquoi': (
            'Échanges, démo, jusqu’à la signature d’un devis et un client actif.'
        ),
        'dependance': 'Sans venture active et livrable, on vend du vent.',
        'comment': (
            'Qualification, conversation, prix : mêmes kinds que le smoke,'
            ' autre etape_id.'
        ),
    },
    'collect_feedback': {
        'titre': 'Collect feedback',
        'pourquoi': (
            'Mails, transcripts, réseaux, leçons — améliorer le livrable ou Serge.'
        ),
        'dependance': 'Sans échanges, rien à consolider.',
        'comment': 'Work items mémoire et invocations de consolidation.',
    },
    'caisse': {
        'titre': 'Caisse',
        'pourquoi': (
            'L’euro entre (Stripe, devis payé). Dunning et relances d’encaissement.'
        ),
        'dependance': (
            'Sans client / devis, encaisser ce serait vendre du vent.'
        ),
        'comment': (
            'Pas une invocation LLM qui « crée l’argent ». Le rail encaisse ;'
            ' les règles autorisent ou refusent.'
        ),
    },
}


def _court(nom: str) -> str:
    role = role_de(nom)[0]
    tete, sep, _ = role.partition('.')
    return (tete + '.') if sep else role


def _points() -> dict[str, dict]:
    try:
        from serge.registry import load_llm_points

        return load_llm_points()
    except Exception:
        return {}


def lister_jugements(
    etape: str, chauds: set[str] | None = None
) -> list[dict[str, Any]]:
    """Jugements d’une étape : d’abord l’ordre, puis le reste à part.

    Args:
        etape: Id d’étape (`ecoute`, `hypothese`, …).
        chauds: Points vus récemment (badge).

    Returns:
        Lignes `{id, titre, detail, rang, ordre, chaud}`.
    """
    chauds = chauds or set()
    registres = _points()
    suite = [n for n in ORDRE.get(etape, []) if n in registres]
    connus = [
        n for n, et in LLM_ETAPE.items() if et == etape and n in registres
    ]
    reste = [n for n in connus if n not in suite]
    lignes = []
    for i, nom in enumerate(suite, 1):
        lignes.append(
            {
                'id': nom,
                'titre': titre_llm(nom),
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
                'titre': titre_llm(nom),
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
    spec = ETAPES.get(ident)
    if spec is None:
        return None
    chauds = {
        str(r[0])
        for r in conn.execute(
            'SELECT DISTINCT point FROM llm_usage ORDER BY id DESC LIMIT 20'
        ).fetchall()
    }
    jugs = lister_jugements(ident, chauds)
    prec = PRECEDENTE.get(ident)
    titre_prec = ETAPES[prec]['titre'] if prec and prec in ETAPES else ''
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
    return {
        'type': 'etape',
        'id': ident,
        'titre': spec['titre'],
        'pourquoi': spec['pourquoi'],
        'champs': [
            {'k': 'Invocations LLM', 'v': str(len(jugs))},
            {'k': 'Invocations techniques', 'v': str(len(tech_liens))},
            {'k': 'Étape d’avant', 'v': titre_prec or '— (début)'},
        ],
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
