#!/usr/bin/env python3
"""Mission Control : la carte du pipeline (page Carte).

Tout ce que la base dit du pipeline, à plat : chaque invocation, ce qui la
lance (un bouton, une horloge, une ligne écrite dans une table), les
tables qu'elle lit et celles où elle écrit, ses outils, les liens vers les
invocations suivantes et les missions qu'elle confie. Rien n'est écrit
ici à la main : une invocation, un lien ou un outil ajouté en base
apparaît sur la carte au passage suivant du flux.

Deux onglets, découpés par ce que disent les liens et les déclencheurs :

- **le pipeline principal** : les invocations des étapes, celles qu'une
  horloge ou une écriture lance, et tout ce que leurs liens atteignent
  (hors couloir d'essai). Une invocation qui ne sert qu'en mission y est
  aussi, au bout de son trait ;
- **les essais et les boutons** : les petites chaînes qu'un bouton lance
  à part (l'essai total, les essais des réseaux, les comptes web), et les
  liens du couloir d'essai. Une invocation du pipeline principal qu'elles
  rejoignent y est montrée en fantôme.

Ce qu'une invocation écrit vient de ses règles d'écriture
(``invocation_writes``) ; ce que le code d'une capacité écrit de lui-même
(« Envoyer un message » note l'envoi parti) n'est pas décrit en base, donc
pas sur la carte.

``project_carte`` rend la carte ; ``project_carte_etat`` la dernière
exécution de chaque invocation, qui change bien plus souvent.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.mc.carte_lecture import (
    declencheurs,
    ecritures,
    invocations,
    lire_liens,
    outils,
    titres_des_tables,
)
from serge.mc.carte_plan import poser

HORS_ETAPE = 'hors_etape'


def _principal(
    noeuds: Mapping[str, dict[str, Any]], liens: list[dict[str, Any]]
) -> set[str]:
    """Les invocations qui tournent dans le pipeline principal : celles
    des étapes, celles qu'une horloge ou une écriture lance, celles que
    rien en base ne lance (le code les appelle), et tout ce que leurs
    liens atteignent hors du couloir d'essai."""
    arrivees = {lien['vers'] for lien in liens}
    en_mission = {
        outil['mission']
        for case in noeuds.values()
        for outil in case['outils']
        if outil['mission']
    }
    racines = [
        ident
        for ident, case in noeuds.items()
        if case['etape']
        or any(
            d['sorte'] != 'bouton' and d['couloir'] != 'trial'
            for d in case['lance']
        )
        or (not case['lance'] and ident not in arrivees | en_mission)
    ]
    dedans = set(racines)
    a_voir = list(racines)
    while a_voir:
        courant = a_voir.pop()
        for lien in liens:
            if (
                lien['de'] == courant
                and lien['couloir'] != 'trial'
                and lien['vers'] not in dedans
            ):
                dedans.add(lien['vers'])
                a_voir.append(lien['vers'])
    return dedans


def _essais(
    noeuds: Mapping[str, dict[str, Any]],
    liens: list[dict[str, Any]],
    principal: set[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Les cases et les liens de l'onglet des essais : ce qu'un bouton
    lance à part, et les liens du couloir d'essai. La chaîne s'arrête où
    elle rejoint le pipeline principal."""
    dedans = [
        ident
        for ident, case in noeuds.items()
        if ident not in principal
        and any(d['sorte'] == 'bouton' for d in case['lance'])
    ]
    vus = set(dedans)
    gardes = []
    a_voir = list(dedans)

    def ajoute(ident: str, suite: bool) -> None:
        if ident not in vus:
            vus.add(ident)
            dedans.append(ident)
            if suite:
                a_voir.append(ident)

    for lien in liens:
        if lien['couloir'] == 'trial':
            gardes.append(lien)
            ajoute(lien['de'], lien['de'] not in principal)
            ajoute(lien['vers'], lien['vers'] not in principal)
    while a_voir:
        courant = a_voir.pop()
        for lien in liens:
            if lien['de'] == courant and lien not in gardes:
                gardes.append(lien)
                ajoute(lien['vers'], lien['vers'] not in principal)
    return dedans, gardes


def _chaines(ids: list[str], liens: list[dict[str, Any]]) -> list[list[str]]:
    """Les cases rangées par chaîne : deux cases reliées sont de la même."""
    chef = {i: i for i in ids}

    def racine(ident: str) -> str:
        while chef[ident] != ident:
            chef[ident] = chef[chef[ident]]
            ident = chef[ident]
        return ident

    for lien in liens:
        if lien['de'] in chef and lien['vers'] in chef:
            chef[racine(lien['de'])] = racine(lien['vers'])
    chaines: dict[str, list[str]] = {}
    for ident in ids:
        chaines.setdefault(racine(ident), []).append(ident)
    return list(chaines.values())


def _onglet(
    bandes: list[dict[str, Any]],
    cases: dict[str, dict[str, Any]],
    liens: list[dict[str, Any]],
) -> dict[str, Any]:
    plan = poser(bandes, cases, [(lien['de'], lien['vers']) for lien in liens])
    return {**plan, 'noeuds': list(cases.values()), 'liens': liens}


def project_carte(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """La carte du pipeline, en deux onglets.

    Returns:
        ``{principal, essais}``, chacun ``{bandes, noeuds, liens, largeur,
        hauteur}``. Une case : son id, son titre, sa sorte, ce qui la
        lance, ce qu'elle lit, ce qu'elle écrit, ses outils, et sa place
        (``x, y, w, h, carte_y``). Un lien : ``de``, ``vers``, sa sorte
        (``lien`` ou ``mission``), sa condition, son couloir.
    """
    _ = (policy, now)
    tables = titres_des_tables(conn)
    noeuds = invocations(conn)
    declencheurs(conn, noeuds)
    missions = outils(conn, noeuds, tables)
    ecritures(conn, noeuds, tables)
    liens = lire_liens(conn, noeuds)
    principal = _principal(noeuds, liens)
    # Le pipeline principal : ses invocations, plus celles qui n'y servent
    # qu'en mission, au bout de leur trait.
    en_mission = {
        m['vers'] for m in missions if m['de'] in principal
    } - principal
    etapes = [
        (str(r[0]), str(r[1] or r[0]))
        for r in conn.execute(
            'SELECT id, titre FROM pipeline_steps ORDER BY rang, id'
        )
    ]
    # L'ordre de la base dans chaque bande : celui des lignes.
    ordre = {ident: n for n, ident in enumerate(noeuds)}
    bandes: list[dict[str, Any]] = [
        {
            'id': etape,
            'titre': f'{numero}. {titre}',
            'noeuds': sorted(
                (i for i in principal if noeuds[i]['etape'] == etape),
                key=ordre.__getitem__,
            ),
        }
        for numero, (etape, titre) in enumerate(etapes, 1)
    ]
    connues = {etape for etape, _ in etapes}
    bandes.append(
        {
            'id': HORS_ETAPE,
            'titre': 'Hors étape',
            'sous_titre': 'Les conversations, et ce qui sert à plusieurs'
            ' étapes.',
            'noeuds': [
                i
                for i in noeuds
                if (i in principal and noeuds[i]['etape'] not in connues)
                or i in en_mission
            ],
        }
    )
    dans_principal = principal | en_mission
    liens_principaux = [
        lien
        for lien in [*liens, *missions]
        if lien.get('couloir') != 'trial'
        and lien['de'] in dans_principal
        and lien['vers'] in dans_principal
        and (lien['sorte'] == 'mission' or lien['de'] in principal)
    ]
    cases = {
        i: {**noeuds[i], 'mission_seule': i in en_mission}
        for i in noeuds
        if i in dans_principal
    }
    essais, liens_essais = _essais(noeuds, liens, principal)
    # Une case du pipeline principal qu'un essai rejoint : en fantôme,
    # sans ses rangées (elles sont dans l'autre onglet).
    cases_essais = {
        i: {**noeuds[i], 'fantome': True, 'lance': [], 'lit': [], 'ecrit': []}
        if i in principal
        else {**noeuds[i], 'fantome': False}
        for i in sorted(essais, key=ordre.__getitem__)
    }
    bandes_essais = []
    couloir: list[str] = []
    for chaine in _chaines(list(cases_essais), liens_essais):
        boutons = [
            d['titre']
            for i in chaine
            if i not in principal
            for d in noeuds[i]['lance']
            if d['sorte'] == 'bouton'
        ]
        if not boutons:
            couloir += chaine
            continue
        bandes_essais.append(
            {
                'id': f'essai:{chaine[0]}',
                'titre': ' · '.join(dict.fromkeys(boutons)),
                'sous_titre': 'Une chaîne lancée par un bouton.',
                'noeuds': chaine,
            }
        )
    if couloir:
        bandes_essais.append(
            {
                'id': 'couloir',
                'titre': 'Couloir d’essai',
                'sous_titre': 'Les liens qui ne jouent que pendant un'
                ' essai total, entre des invocations du pipeline'
                ' principal.',
                'noeuds': couloir,
            }
        )
    return {
        'principal': _onglet(bandes, cases, liens_principaux),
        'essais': _onglet(bandes_essais, cases_essais, liens_essais),
    }


def project_carte_etat(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now: str
) -> dict[str, Any]:
    """La dernière exécution de chaque invocation : la dernière tâche
    partie (en cours, finie, en échec…), avec son heure et son erreur.

    Returns:
        ``{invocations: {id: {tache, statut, commencee, finie, erreur}}}``.
    """
    _ = (policy, now)
    return {
        'invocations': {
            str(r[0]): {
                'tache': str(r[1]),
                'statut': str(r[2]),
                'commencee': str(r[3] or ''),
                'finie': str(r[4] or ''),
                'erreur': str(r[5] or ''),
            }
            for r in conn.execute(
                'SELECT t.invocation_id, t.id, t.status, t.started_at,'
                ' t.finished_at, t.last_error FROM tasks t JOIN ('
                "SELECT MAX(rowid) AS r FROM tasks WHERE status<>'ready'"
                ' GROUP BY invocation_id) d ON d.r=t.rowid'
            )
        }
    }
