#!/usr/bin/env python3
"""La carte du pipeline : où poser chaque invocation.

La carte est faite de **bandes** horizontales, l'une sous l'autre : une
bande par étape du pipeline, dans l'ordre des étapes, ou une bande par
petite chaîne d'essai. Dans une bande, les invocations se lisent de gauche
à droite, dans l'ordre de leurs liens : une invocation est placée à droite
de celles qui mènent à elle. Deux invocations de même rang sont l'une sous
l'autre.

Une invocation occupe une **case** : sa carte, et autour d'elle des
rangées qui ne sont là que si elles servent. De haut en bas : ce qui la
lance, les tables qu'elle lit, sa carte, les tables où elle écrit. La
page (``static/mc/pages/carte.js``, ``style-carte.css``) dessine ces
rangées aux mêmes hauteurs : les nombres de ce fichier et ceux de la
feuille de style vont ensemble.

Exemple : dans la bande « Pré-prospection », « Ouvrir un cycle » mène à
« Explorer le web », qui mène à « Trier les pages » : trois cases côte à
côte, aux rangs 0, 1 et 2.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

# La largeur d'une case, et la place entre deux cases.
LARGEUR = 270
ECART_X = 90
ECART_Y = 26
# La hauteur de chaque rangée d'une case.
H_LANCE = 26
H_TABLES = 46
H_CARTE = 68
# Autour des cases d'une bande : son titre, puis sa marge.
TITRE_BANDE = 44
MARGE = 24
ECART_BANDES = 28
# Une bande a au plus tant de colonnes par étage ; les cases que rien ne
# relie se rangent par colonnes de tant de cases.
COLONNES_MAX = 8
SEULES_PAR_COLONNE = 3


def hauteur(noeud: Mapping[str, Any]) -> tuple[int, int]:
    """La hauteur d'une case, et où commence sa carte dans la case."""
    avant = (H_LANCE if noeud.get('lance') else 0) + (
        H_TABLES if noeud.get('lit') else 0
    )
    apres = H_TABLES if noeud.get('ecrit') else 0
    return avant + H_CARTE + apres, avant


def rangs(
    ids: Sequence[str], liens: Iterable[tuple[str, str]]
) -> dict[str, int]:
    """Le rang de chaque invocation d'une bande : 0 pour celles que rien
    ne précède, sinon un de plus que la plus à droite de celles qui mènent
    à elle. Un lien qui revient en arrière (une boucle : critiquer, puis
    corriger) ne compte pas.
    """
    dedans = set(ids)
    suivants: dict[str, list[str]] = {i: [] for i in ids}
    for de, vers in liens:
        if de in dedans and vers in dedans and de != vers:
            suivants[de].append(vers)
    # Un parcours en profondeur, dans l'ordre de la base : un lien vers
    # une invocation encore en cours de visite ferme une boucle.
    etat: dict[str, int] = {}
    avant: dict[str, list[str]] = {i: [] for i in ids}
    for depart in ids:
        if depart in etat:
            continue
        pile = [(depart, iter(suivants[depart]))]
        etat[depart] = 1
        while pile:
            courant, reste = pile[-1]
            suivant = next(reste, None)
            if suivant is None:
                etat[courant] = 2
                pile.pop()
            elif suivant not in etat:
                avant[suivant].append(courant)
                etat[suivant] = 1
                pile.append((suivant, iter(suivants[suivant])))
            elif etat[suivant] == 2:
                avant[suivant].append(courant)
    rang: dict[str, int] = {}

    def calcule(ident: str) -> int:
        if ident not in rang:
            rang[ident] = 0
            rang[ident] = max(
                (calcule(p) + 1 for p in avant[ident]), default=0
            )
        return rang[ident]

    for ident in ids:
        calcule(ident)
    return rang


def _chaines(
    ids: Sequence[str], liens: Iterable[tuple[str, str]]
) -> tuple[list[list[str]], list[str]]:
    """Les cases d'une bande, par chaîne (des cases reliées entre elles),
    et celles qu'aucun lien de la bande ne relie."""
    chef = {i: i for i in ids}

    def racine(ident: str) -> str:
        while chef[ident] != ident:
            chef[ident] = chef[chef[ident]]
            ident = chef[ident]
        return ident

    for de, vers in liens:
        if de in chef and vers in chef:
            chef[racine(de)] = racine(vers)
    groupes: dict[str, list[str]] = {}
    for ident in ids:
        groupes.setdefault(racine(ident), []).append(ident)
    chaines = [g for g in groupes.values() if len(g) > 1]
    seules = [g[0] for g in groupes.values() if len(g) == 1]
    return chaines, seules


def _colonnes(
    ids: Sequence[str], liens: Sequence[tuple[str, str]]
) -> list[list[str]]:
    """Les colonnes d'une chaîne, de gauche à droite. Dans une colonne,
    une case suit, autant que possible, la hauteur de celles qui mènent à
    elle : les liens se croisent moins."""
    rang = rangs(ids, liens)
    colonnes: dict[int, list[str]] = {}
    for ident in ids:
        colonnes.setdefault(rang[ident], []).append(ident)
    place: dict[str, float] = {}
    rendues = []
    for numero in sorted(colonnes):
        colonne = colonnes[numero]
        depart = {ident: float(n) for n, ident in enumerate(colonne)}

        def poids(ident: str, depart: dict[str, float] = depart) -> float:
            amont = [
                place[de]
                for de, vers in liens
                if vers == ident and de in place
            ]
            return sum(amont) / len(amont) if amont else depart[ident]

        colonne.sort(key=poids)
        for position, ident in enumerate(colonne):
            place[ident] = float(position)
        rendues.append(colonne)
    return rendues


def poser(
    bandes: Sequence[Mapping[str, Any]],
    noeuds: Mapping[str, dict[str, Any]],
    liens: Sequence[tuple[str, str]],
) -> dict[str, Any]:
    """Pose les cases de chaque bande et rend les bandes avec leur place.

    Dans une bande, chaque chaîne (des cases reliées entre elles) a ses
    colonnes ; les chaînes se suivent de gauche à droite, puis les cases
    que rien ne relie, par petites colonnes. Une bande trop large continue
    à l'étage du dessous.

    Args:
        bandes: ``[{id, titre, sous_titre, noeuds: [id…]}]``, dans l'ordre
            de haut en bas.
        noeuds: Les cases par id ; chacune reçoit ``x``, ``y``, ``w``,
            ``h`` et ``carte_y`` (où commence sa carte dans la case).
        liens: Les liens ``(de, vers)`` qui rangent les cases.

    Returns:
        ``{bandes: [{id, titre, sous_titre, x, y, w, h}], largeur,
        hauteur}``.
    """
    posees = []
    haut = MARGE
    colonnes_max = 1
    for bande in bandes:
        ids = [i for i in bande['noeuds'] if i in noeuds]
        if not ids:
            continue
        chaines, seules = _chaines(ids, liens)
        blocs = [_colonnes(chaine, liens) for chaine in chaines]
        if seules:
            blocs.append(
                [
                    seules[n : n + SEULES_PAR_COLONNE]
                    for n in range(0, len(seules), SEULES_PAR_COLONNE)
                ]
            )
        y_etage = haut + TITRE_BANDE
        colonne = 0
        bas_etage = y_etage
        for bloc in blocs:
            if colonne and colonne + len(bloc) > COLONNES_MAX:
                # La bande est pleine : la suite à l'étage du dessous.
                y_etage = bas_etage + ECART_Y * 2
                colonne = 0
            for cases in bloc:
                y = y_etage
                for ident in cases:
                    case = noeuds[ident]
                    h, carte_y = hauteur(case)
                    case.update(
                        x=MARGE * 2 + colonne * (LARGEUR + ECART_X),
                        y=y,
                        w=LARGEUR,
                        h=h,
                        carte_y=carte_y,
                    )
                    y += h + ECART_Y
                bas_etage = max(bas_etage, y - ECART_Y)
                colonne += 1
                colonnes_max = max(colonnes_max, colonne)
        posees.append(
            {
                'id': bande['id'],
                'titre': bande['titre'],
                'sous_titre': bande.get('sous_titre', ''),
                'x': MARGE,
                'y': haut,
                'h': bas_etage - haut + MARGE,
            }
        )
        haut = bas_etage + MARGE + ECART_BANDES
    # Toutes les bandes ont la largeur de la plus large : la carte se lit
    # comme une suite de lignes.
    largeur = MARGE * 2 + colonnes_max * (LARGEUR + ECART_X) - ECART_X + MARGE
    for bande in posees:
        bande['w'] = largeur
    return {
        'bandes': posees,
        'largeur': largeur + MARGE * 2,
        'hauteur': haut,
    }
