#!/usr/bin/env python3
"""Étapes de la chaîne : textes, invocations dans l'ordre des liens, fiche MC.

L'ordre des invocations d'une étape n'est écrit nulle part dans le code :
il suit les liens en base. Exemple : si « Ouvrir un cycle » passe la main
à « Explorer A », qui passe la main à « Choisir », la fiche les montre dans
cet ordre. Une invocation lancée par un déclencheur ouvre la liste ; une
invocation sans lien ni déclencheur est rangée à part.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.etape_fiches import fiche_etape, precedente
from serge.etapes import ETAPE_IDS


def _court(role: str) -> str:
    tete, sep, _ = role.partition('.')
    return (tete + '.') if sep else role


def _ordre(
    ids: list[str], aretes: list[tuple[str, str]], entrees: set[str]
) -> list[str]:
    """Ordre des liens (le plus tôt d'abord, à égalité par id).

    Une chaîne de liens passe avant une invocation isolée, lancée seulement
    par un déclencheur (exemple : le cycle d'écoute avant la veille).
    """
    enchainees = {a for arete in aretes for a in arete}
    lies = enchainees | entrees
    restants = {i for i in ids if i in lies}
    ordre: list[str] = []
    while restants:
        prets = sorted(
            (
                i
                for i in restants
                if not any(b == i and a in restants for a, b in aretes)
            ),
            key=lambda i: (i not in enchainees, i),
        )
        # Une boucle de liens : on la coupe au plus petit id.
        suivant = prets[0] if prets else min(restants)
        ordre.append(suivant)
        restants.remove(suivant)
    return ordre


def lister_invocations(
    conn: sqlite3.Connection, etape: str, chauds: set[str] | None = None
) -> list[dict[str, Any]]:
    """Invocations d'une étape : d'abord l'ordre des liens, puis le reste.

    Args:
        conn: Connexion à la base.
        etape: Id d'étape.
        chauds: Invocations passées récemment (badge).

    Returns:
        Lignes ``{id, titre, detail, rang, ordre, chaud, marche}``.
    """
    chauds = chauds or set()
    rows = conn.execute(
        'SELECT id, title, role, enabled FROM invocations'
        " WHERE step_id=? AND deleted_at='' ORDER BY id",
        (etape,),
    ).fetchall()
    infos = {
        str(r[0]): (str(r[1] or r[0]), str(r[2]), bool(r[3])) for r in rows
    }
    ids = list(infos)
    aretes = [
        (str(a), str(b))
        for a, b in conn.execute(
            'SELECT from_invocation_id, to_invocation_id FROM links'
            " WHERE enabled=1 AND deleted_at=''"
        ).fetchall()
        if str(a) in infos and str(b) in infos
    ]
    entrees = {
        str(r[0])
        for r in conn.execute(
            "SELECT invocation_id FROM triggers WHERE deleted_at=''"
        ).fetchall()
    }
    suite = _ordre(ids, aretes, entrees)
    reste = [i for i in ids if i not in suite]
    lignes = []
    for rang, ident in enumerate(suite + reste, 1):
        titre, role, marche = infos[ident]
        dans_ordre = ident in suite
        lignes.append(
            {
                'id': ident,
                'titre': titre,
                'detail': _court(role),
                'rang': rang if dans_ordre else 0,
                'ordre': dans_ordre,
                'chaud': ident in chauds,
                'marche': marche,
            }
        )
    return lignes


def invocations_chaudes(conn: sqlite3.Connection) -> set[str]:
    """Les invocations passées parmi les 20 dernières tâches."""
    return {
        str(r[0])
        for r in conn.execute(
            'SELECT invocation_id FROM tasks'
            " WHERE status IN ('running', 'done', 'failed')"
            " ORDER BY COALESCE(NULLIF(finished_at, ''), started_at) DESC"
            ' LIMIT 20'
        ).fetchall()
    }


def project_etape(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Fiche d'une étape : rôle, étape d'avant, invocations cliquables.

    Args:
        conn: Connexion à la base.
        ident: Id d'étape.

    Returns:
        Contenu de la fiche, ou None si l'étape est inconnue.
    """
    if ident not in ETAPE_IDS:
        return None
    spec = fiche_etape(conn, ident)
    if spec is None:
        return None
    invs = lister_invocations(conn, ident, invocations_chaudes(conn))
    prec = precedente(conn, ident)
    prec_fiche = fiche_etape(conn, prec) if prec else None
    titre_prec = (prec_fiche or {}).get('titre') or ''
    liens_ord = [
        {'type': 'llm', 'id': j['id'], 'titre': f'{j["rang"]}. {j["titre"]}'}
        for j in invs
        if j['ordre']
    ]
    liens_reste = [
        {'type': 'llm', 'id': j['id'], 'titre': j['titre']}
        for j in invs
        if not j['ordre']
    ]
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
            'titre': 'Invocations, dans l’ordre des liens',
            'texte': (
                'Chaque ligne ouvre la page de l’invocation.'
                if liens_ord
                else 'Aucune invocation reliée dans cette étape pour'
                ' l’instant.'
            ),
            'liens': liens_ord,
        },
    ]
    if liens_reste:
        cadres.append(
            {
                'titre': 'Autres invocations (sans lien ni déclencheur)',
                'liens': liens_reste,
            }
        )
    if ident == 'pre_prospection':
        cadres.append(
            {
                'titre': 'Voir aussi',
                'liens': [
                    {
                        'type': 'ecoute',
                        'id': 'pages',
                        'titre': 'Pages vraiment lues (miroir)',
                    }
                ],
            }
        )
    return {
        'type': 'etape',
        'id': ident,
        'titre': spec['titre'],
        'pourquoi': spec['pourquoi'],
        'champs': [
            {'k': 'Invocations', 'v': str(len(invs))},
            {'k': 'Étape d’avant', 'v': titre_prec or '— (début)'},
            {'k': 'Dernière modification', 'v': spec['updated_at'] or '—'},
        ],
        'cadres': cadres,
        'enfants': [],
        'preuve': '',
    }
