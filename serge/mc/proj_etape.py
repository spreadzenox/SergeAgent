#!/usr/bin/env python3
"""Étapes du pipe : textes, ordre des jugements, fiche MC."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.mc.libelles import LLM_ETAPE, titre_llm
from serge.mc.llm_roles import role_de

# Ordre d’exécution réel (pas l’ordre du YAML). Le reste = « à part ».
ORDRE: dict[str, list[str]] = {
    'ecoute': ['cluster_demand'],
    'hypothese': [
        'draft_hypothesis_smoke',
        'resume_test',
        'draft_hypothesis_full',
    ],
    'test': [
        'plan_scale',
        'options_pivot',
        'build_artifact',
        'review_build',
        'summarize_build_debt',
    ],
    'qualif': [
        'qualify_prospect',
        'fill_slots',
        'score_lead_departage',
    ],
    'conversation': [
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
    ],
    'intent': ['draft_price', 'judge_allocator'],
    'caisse': [],
}

PRECEDENTE = {
    'ecoute': None,
    'hypothese': 'ecoute',
    'test': 'hypothese',
    'qualif': 'test',
    'conversation': 'qualif',
    'intent': 'conversation',
    'caisse': 'intent',
}

ETAPES: dict[str, dict[str, str]] = {
    'ecoute': {
        'titre': 'Écoute',
        'pourquoi': (
            'Serge lit ce que des inconnus ont déjà écrit (forums, flux RSS…).'
            ' But : sentir une demande réelle, pas inventer une idée.'
        ),
        'dependance': 'Rien avant. C’est le début du pipe.',
        'comment': (
            'Aujourd’hui : ramasser des pages (surtout des flux), les ranger'
            ' en base, puis un jugement les met en paquets nommés.'
            ' Un navigateur (Brave) n’est pas encore un bouton du jugement.'
            ' Les pages elles-mêmes sont un miroir à part — pas cette étape.'
        ),
    },
    'hypothese': {
        'titre': 'Idée de business',
        'pourquoi': (
            'On écrit le pari avant d’agir : quoi vendre, à quel prix,'
            ' par quel canal, à combien de gens, pendant combien de jours.'
        ),
        'dependance': (
            'Sans paquets de demandes (étape Écoute), on n’a rien à tester'
            ' — juste une intuition.'
        ),
        'comment': (
            'D’abord une petite idée à essayer. Après le premier essai,'
            ' on raconte les vrais chiffres, puis on décide si on agrandit.'
            ' Toi tu valides souvent ici : une mauvaise idée se propage partout.'
        ),
    },
    'test': {
        'titre': 'Essai',
        'pourquoi': (
            'On parle à un nombre de personnes décidé d’avance, on mesure,'
            ' on ne change pas les règles en cours de route.'
        ),
        'dependance': (
            'Sans idée écrite (offre, prix, canal, N), on ne saurait pas'
            ' ce qu’on mesure.'
        ),
        'comment': (
            'Des campagnes partent (e-mail, appel…). Si ça marche : comment'
            ' grandir. Si ça perd : trois autres idées. Parfois on construit'
            ' un livrable. Les compteurs sont dans la base, pas dans le modèle.'
        ),
    },
    'qualif': {
        'titre': 'Qualification',
        'pourquoi': 'Ne perdre du temps (et des e-mails) que sur les gens dans la cible.',
        'dependance': (
            'Sans essai en cours, « dans la cible » ne veut rien dire :'
            ' cible de quoi ?'
        ),
        'comment': (
            'Un jugement dit oui/non pour une personne. On remplit les cases'
            ' encore vides (besoin, ville…). S’il faut départager deux pistes,'
            ' un autre jugement choisit.'
        ),
    },
    'conversation': {
        'titre': 'Conversation',
        'pourquoi': (
            'Répondre, relancer, proposer un créneau, parfois appeler.'
            ' C’est ici qu’une prise de contact devient un vrai échange.'
        ),
        'dependance': (
            'On n’écrit qu’aux gens déjà gardés. Sinon on spam des hors-cible.'
        ),
        'comment': (
            'Quelqu’un répond : on classe le message, on extrait un rendez-vous'
            ' s’il y en a un, on relance ou on répond. L’oral a ses propres'
            ' jugements (script, réplique, note d’appel).'
        ),
    },
    'intent': {
        'titre': 'Intention',
        'pourquoi': (
            'Le signal d’achat : devis, « oui », objection prix, rendez-vous.'
            ' Sans ça, pas de facture.'
        ),
        'dependance': (
            'L’intention naît dans la conversation. On ne l’invente pas'
            ' à partir d’un silence.'
        ),
        'comment': (
            'On propose un prix dans les bornes. Un autre jugement dit où'
            ' mettre l’effort (cette piste, ou une autre) — sans signer'
            ' à ta place.'
        ),
    },
    'caisse': {
        'titre': 'Caisse',
        'pourquoi': (
            'L’euro entre (Stripe, devis payé). C’est le bout du pipe :'
            ' tout le reste sert ça.'
        ),
        'dependance': (
            'Sans intention claire, encaisser ce serait vendre du vent'
            ' ou relancer au hasard.'
        ),
        'comment': (
            'Pas un jugement qui « crée l’argent ». Le rail (Stripe) encaisse ;'
            ' les règles décident si on peut prendre l’argent. Les jugements'
            ' sont surtout avant (prix, allocation).'
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
    if ident == 'ecoute':
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
    return {
        'type': 'etape',
        'id': ident,
        'titre': spec['titre'],
        'pourquoi': spec['pourquoi'],
        'champs': [
            {'k': 'Jugements liés', 'v': str(len(jugs))},
            {'k': 'Étape d’avant', 'v': titre_prec or '— (début)'},
        ],
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
