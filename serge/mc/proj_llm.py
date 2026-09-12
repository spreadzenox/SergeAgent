#!/usr/bin/env python3
"""Fiches jugement : rôle clair, flux, lectures, outils, invocations."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from serge.mc.libelles import titre_llm
from serge.mc.llm_roles import role_de, texte_materiel, titre_materiel

PALIERS = {
    'T1': 'Petit et rapide — un réflexe (classer, extraire). Moins cher.',
    'T2': 'Moyen — assez malin pour rédiger ou nommer, sans être le plus cher.',
    'T3': 'Le plus malin (et le plus cher) — plans, arbitrages, changements de cap.',
}

VERDICTS = {
    'HYB': (
        'Travail en deux temps : d’abord un tri automatique (textes'
        ' qui se ressemblent), ensuite le modèle pose un nom dessus.'
    ),
    'LLM-1': 'Un jugement simple à une réponse (classe, oui/non, date).',
    'LLM-B': 'Il rédige un texte dans un moule (idée, message, script).',
    'LLM-L': 'Il réfléchit plus large (plan, options, où mettre l’argent).',
    'LLM-R': 'Il relit ou résume — il n’invente pas de chiffres.',
}

REPLIS = {
    'clusters bruts sans labels': (
        'Si le modèle n’y arrive pas : on garde les tas de textes'
        ' comme ils sont, sans leur donner un joli nom.'
    ),
    'template min + ticket QNA': 'On pose un moule vide et on te pose la question.',
    'chiffres bruts sans résumé': 'On affiche les nombres, sans histoire autour.',
    'rejouer le test gagnant à l’identique + FYI': (
        'On refait ce qui a déjà marché, et on te prévient.'
    ),
    'règles ICP de base': (
        'Critères minimum « cette personne ressemble-t-elle à la cible ? ».'
    ),
    'PIVOT → EXTEND (variation min) + FYI + QNA optionnel': (
        'On garde l’essai, on varie un peu, on te prévient, parfois une question.'
    ),
}

NOTIONS = {
    'grappe': (
        'Un paquet de demandes',
        'Imagine 40 messages différents. Certains disent « je veux un'
        ' timer pour facturer », d’autres « un chrono freelance » :'
        ' c’est la même envie. Serge les met dans le même paquet et'
        ' lui donne un nom en français. Ce n’est pas une table magique :'
        ' c’est juste « ces gens-là veulent la même chose ».',
    ),
    'score_volume': (
        'La note de volume',
        'Une note simple : on en voit beaucoup, ou presque pas.'
        ' Beaucoup + souvent + des gens prêts à payer = une idée'
        ' plus intéressante qu’un message unique. Ce n’est pas un'
        ' classement Instagram : c’est « est-ce que ça se répète ? ».',
    ),
}

OUTILS = {
    'memory_search': (
        'Chercher dans la mémoire',
        'L’outil prévu pour fouiller la mémoire : leçons,'
        ' vieux échanges, pages lues. Aujourd’hui le contrat dit'
        ' quoi aller chercher. La recherche libre'
        ' (tu poses une question, il ramène 5 extraits) est dans'
        ' l’architecture ; le câblage runtime se complète.',
    ),
    'couche5': (
        'Demander un complément',
        'Si le dossier prévu ne suffit pas, le jugement a le droit'
        ' de demander un peu plus — dans un budget (jetons, délai).'
        ' C’est la soupape : il n’est pas prisonnier d’une page figée.'
        ' Lecture seule : ça informe, ça n’écrit pas.',
    ),
    'navigateur': (
        'Ouvrir le web (navigateur)',
        'Un vrai navigateur (Brave / Chromium) pour aller voir une'
        ' page, un fil Reddit, un profil. Pas encore branché comme'
        ' outil du jugement. Aujourd’hui Serge ramasse surtout des'
        ' flux RSS. Un budget navigateur existe déjà dans les règles.'
        ' À brancher.',
    ),
    'demande_capacite': (
        'Demander une nouvelle capacité',
        'Quand Serge ne peut pas (pas de canal, pas d’outil), il'
        ' doit poser un ticket « j’ai besoin de X » plutôt que'
        ' d’inventer. C’est dans l’esprit du système ; la page'
        ' d’outils du jugement le montre pour ne pas l’oublier.',
    ),
}


def _points() -> dict[str, dict]:
    try:
        from serge.registry import load_llm_points

        return load_llm_points()
    except Exception:
        return {}


def _dernier_io(conn: sqlite3.Connection, nom: str) -> tuple[str, str]:
    row = conn.execute(
        "SELECT payload_json FROM events WHERE type='llm.io'"
        " AND payload_json LIKE ? ORDER BY id DESC LIMIT 1",
        (f'%{nom}%',),
    ).fetchone()
    if not row:
        return '', ''
    try:
        blob = json.loads(row[0])
    except ValueError:
        return '', ''
    if not isinstance(blob, dict):
        return '', ''
    if blob.get('point') and blob.get('point') != nom:
        return '', ''
    return str(blob.get('prompt') or ''), str(blob.get('sortie') or '')


def _ecoute_etat(conn: sqlite3.Connection) -> tuple[int, str]:
    n = int(conn.execute('SELECT COUNT(*) FROM listen_docs').fetchone()[0])
    srcs = [
        str(r[0])
        for r in conn.execute(
            "SELECT DISTINCT source FROM listen_docs WHERE source!=''"
        ).fetchall()
    ]
    noms = ['flux RSS (Reddit, blogs…)' if s == 'rss' else s for s in srcs]
    return n, (', '.join(noms) if noms else 'aucune source encore')


def _repli(brut: str) -> str:
    cle = (brut or '').replace("'", '’')
    if cle in REPLIS:
        return REPLIS[cle]
    return f'Si le modèle n’y arrive pas, plan B : {cle}.' if cle else '—'


def _liens_flux(ident: str, spec: dict) -> list[dict[str, str]]:
    ctx = spec.get('context') or {}
    cles = ' '.join(
        str(x) for x in list(ctx.get('fixed') or []) + list(ctx.get('retrieved') or [])
    )
    liens: list[dict[str, str]] = []
    if ident == 'cluster_demand' or 'ecoute' in cles or 'verbatim' in cles:
        liens.append({'type': 'ecoute', 'id': 'pages', 'titre': 'Pages vraiment lues'})
    if ident == 'cluster_demand':
        liens += [
            {'type': 'notion', 'id': 'grappe', 'titre': 'C’est quoi un paquet de demandes ?'},
            {'type': 'notion', 'id': 'score_volume', 'titre': 'C’est quoi la note de volume ?'},
        ]
    return liens


def _liens_materiel(spec: dict) -> list[dict[str, str]]:
    ctx = spec.get('context') or {}
    vus: list[str] = []
    for cle in list(ctx.get('fixed') or []) + list(ctx.get('retrieved') or []):
        if str(cle) not in vus:
            vus.append(str(cle))
    return [{'type': 'contexte', 'id': cle, 'titre': titre_materiel(cle)} for cle in vus]


def _outils(spec: dict) -> list[dict[str, str]]:
    ctx = spec.get('context') or {}
    couche = ctx.get('couche5') or {}
    liens = [
        {'type': 'outil', 'id': 'memory_search', 'titre': 'Chercher dans la mémoire'},
        {'type': 'outil', 'id': 'navigateur', 'titre': 'Ouvrir le web (pas encore branché)'},
        {'type': 'outil', 'id': 'demande_capacite', 'titre': 'Demander une nouvelle capacité'},
    ]
    if isinstance(couche, dict) and couche.get('allowed'):
        liens.insert(
            1,
            {
                'type': 'outil',
                'id': 'couche5',
                'titre': 'Demander un complément (autorisé ici)',
            },
        )
    return liens


def project_llm(conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Fiche d’un jugement : rôle, flux, lectures, outils, passages."""
    spec = _points().get(ident)
    if spec is None:
        return None
    role, entrees, sorties, dest, fmt = role_de(ident)
    if ident == 'cluster_demand':
        n, srcs = _ecoute_etat(conn)
        role += (
            f' En ce moment : {n} page(s) en base, sources : {srcs}.'
            ' Clique « Pages vraiment lues » pour le miroir.'
        )
    prompt, sortie = _dernier_io(conn, ident)
    runs = conn.execute(
        'SELECT id, created_at, tokens_in, tokens_out, latency_ms,'
        ' verdict, tier, model FROM llm_usage WHERE point=?'
        ' ORDER BY id DESC LIMIT 20',
        (ident,),
    ).fetchall()
    lignes = []
    for row in runs:
        rid, when, tin, tout, lat, verd, tier, model = row
        lignes.append(
            {
                'id': f'{ident}:{rid}',
                'type': 'llm_usage',
                'cellules': [
                    when or '—',
                    {'ok': 'terminé', 'error': 'raté'}.get(str(verd), verd or '—'),
                    PALIERS.get(str(tier), str(tier or '—')).split(' —')[0],
                    str(int(tin or 0) + int(tout or 0)),
                    f'{int(lat or 0)} ms',
                    model or '—',
                ],
            }
        )
    prompt_txt = prompt or (
        'Pas encore de prompt enregistré pour ce jugement sur'
        ' cette instance. Le texte vit encore dans le code ;'
        ' ici on verra le prochain passage dès qu’un épisode'
        ' sera posé.'
    )
    liens_flux = _liens_flux(ident, spec)
    return {
        'type': 'llm',
        'id': ident,
        'titre': titre_llm(ident),
        'pourquoi': '',
        'champs': [
            {
                'k': 'Quel genre de modèle',
                'v': PALIERS.get(str(spec.get('tier')), str(spec.get('tier'))),
            },
            {
                'k': 'Quelle sorte de jugement',
                'v': VERDICTS.get(
                    str(spec.get('verdict')), str(spec.get('verdict'))
                ),
            },
            {
                'k': 'Si ça rate',
                'v': _repli(str(spec.get('repli') or '')),
            },
            {
                'k': 'Allumé',
                'v': 'oui — ce jugement peut tourner'
                if spec.get('enabled', True)
                else 'non — coupé pour l’instant',
            },
        ],
        'cadres': [
            {'titre': 'À quoi ça sert', 'texte': role},
            {
                'titre': 'D’où ça vient, où ça va',
                'champs': [
                    {'k': 'Entre', 'v': entrees},
                    {'k': 'Sort', 'v': sorties},
                    {'k': 'Ensuite', 'v': dest},
                    {'k': 'À quoi ça ressemble', 'v': fmt},
                ],
                'liens': liens_flux,
            },
            {
                'titre': 'Le texte qu’on lui donne (prompt)',
                'texte': prompt_txt,
                'todo': (
                    'Pouvoir modifier ce texte depuis Mission Control :'
                    ' pas encore branché. On le notera dans un dossier'
                    ' de prompts, avec une revue avant d’appliquer.'
                ),
            },
            {
                'titre': 'La dernière réponse du modèle',
                'texte': sortie
                or 'Pas encore de réponse enregistrée pour ce jugement.',
            },
            {
                'titre': 'Ce qu’il a le droit de lire',
                'texte': (
                    'Le dossier prévu pour ce jugement — pas des noms'
                    ' de variables. Clique une ligne : c’est expliqué.'
                ),
                'liens': _liens_materiel(spec),
            },
            {
                'titre': 'Outils',
                'texte': (
                    'Oui : Serge a une boîte à outils, ce n’est pas'
                    ' juste un pavé de texte. Chercher dans la mémoire,'
                    ' demander un complément, et plus tard un navigateur.'
                    ' Demander une capacité manquante plutôt qu’inventer.'
                ),
                'liens': _outils(spec),
            },
        ],
        'tableau': {
            'titre': 'Passages récents de ce jugement',
            'colonnes': [
                'Quand',
                'Résultat',
                'Genre de modèle',
                'Jetons',
                'Durée',
                'Nom du modèle',
            ],
            'lignes': lignes,
        },
        'enfants': [],
        'preuve': '',
    }


def project_llm_usage(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """Un passage : compteurs + dernier texte s’il existe."""
    point, sep, raw = ident.partition(':')
    if not sep or not raw.isdigit():
        return None
    row = conn.execute(
        'SELECT id, point, tier, model, tokens_in, tokens_out,'
        ' latency_ms, verdict, created_at FROM llm_usage WHERE id=?',
        (int(raw),),
    ).fetchone()
    if row is None or str(row[1]) != point:
        return None
    prompt, sortie = _dernier_io(conn, point)
    return {
        'type': 'llm_usage',
        'id': ident,
        'titre': f'{titre_llm(point)} · passage {raw}',
        'pourquoi': (
            'Un passage unique. Les jetons et la durée sont sûrs.'
            ' Le texte n’est là que si on a enregistré l’épisode.'
        ),
        'champs': [
            {'k': 'Jugement', 'v': titre_llm(point)},
            {'k': 'Quand', 'v': str(row[8] or '—')},
            {'k': 'Sortie courte', 'v': str(row[7] or '—')},
            {
                'k': 'Quel genre de modèle',
                'v': PALIERS.get(str(row[2]), str(row[2] or '—')),
            },
            {'k': 'Nom du modèle', 'v': str(row[3] or '—')},
            {'k': 'Jetons lus', 'v': str(row[4] or 0)},
            {'k': 'Jetons écrits', 'v': str(row[5] or 0)},
            {'k': 'Durée', 'v': f'{int(row[6] or 0)} ms'},
        ],
        'cadres': [
            {
                'titre': 'Texte donné (le plus récent qu’on a)',
                'texte': prompt or '—',
            },
            {
                'titre': 'Réponse (la plus récente qu’on a)',
                'texte': sortie or '—',
            },
        ],
        'enfants': [{'type': 'llm', 'id': point, 'titre': titre_llm(point)}],
        'preuve': '',
    }


def project_contexte(_conn: sqlite3.Connection, ident: str) -> dict[str, Any]:
    """Une lecture autorisée, expliquée en français."""
    return {
        'type': 'contexte',
        'id': ident,
        'titre': titre_materiel(ident),
        'pourquoi': texte_materiel(ident),
        'champs': [],
        'enfants': [],
        'preuve': '',
    }


def project_ecoute(conn: sqlite3.Connection, ident: str = '') -> dict[str, Any]:
    """Miroir des pages vraiment lues."""
    _ = ident
    rows = conn.execute(
        'SELECT id, source, title, excerpt, url, fetched_at FROM listen_docs'
        ' ORDER BY fetched_at DESC LIMIT 80'
    ).fetchall()
    lignes = []
    for row in rows:
        src = 'flux RSS' if row[1] == 'rss' else (row[1] or '—')
        lignes.append(
            {
                'id': row[0],
                'type': 'listen_doc',
                'cellules': [
                    src,
                    row[2] or 'sans titre',
                    (row[3] or '—')[:140],
                    row[5] or '—',
                ],
            }
        )
    todo = ''
    if not lignes:
        todo = (
            'Aucune page en base pour l’instant. Quand Serge écoute'
            ' pour de vrai, elles apparaissent ici (flux RSS aujourd’hui :'
            ' Reddit, blogs…). Un navigateur type Brave n’est pas encore'
            ' branché comme outil du jugement.'
        )
    return {
        'type': 'ecoute',
        'id': 'pages',
        'titre': 'Pages vraiment lues',
        'pourquoi': (
            'C’est le miroir de ce que Serge a ramassé sur internet'
            ' pour sentir une demande. Pas une idée abstraite : des'
            ' titres, des extraits, une source. Clique une ligne.'
        ),
        'champs': [{'k': 'Pages en base', 'v': str(len(lignes))}],
        'tableau': {
            'titre': 'Miroir maintenant',
            'colonnes': ['Source', 'Titre', 'Extrait', 'Quand'],
            'lignes': lignes,
        },
        'cadres': [{'titre': 'À brancher', 'todo': todo}] if todo else [],
        'enfants': [],
        'preuve': '',
    }


def project_outil(_conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Une fiche d’outil (mémoire, complément, navigateur…)."""
    found = OUTILS.get(ident)
    if not found:
        return None
    titre, texte = found
    todo = ''
    if ident in ('navigateur', 'demande_capacite'):
        todo = 'Pas encore un bouton que le jugement peut presser tout seul.'
    return {
        'type': 'outil',
        'id': ident,
        'titre': titre,
        'pourquoi': texte,
        'champs': [],
        'cadres': [{'titre': 'État', 'todo': todo}] if todo else [],
        'enfants': [],
        'preuve': '',
    }


def project_notion(_conn: sqlite3.Connection, ident: str) -> dict[str, Any] | None:
    """Une définition cliquée depuis un flux (paquet, note de volume)."""
    found = NOTIONS.get(ident)
    if not found:
        return None
    titre, texte = found
    return {
        'type': 'notion',
        'id': ident,
        'titre': titre,
        'pourquoi': texte,
        'champs': [],
        'enfants': [],
        'preuve': '',
    }
