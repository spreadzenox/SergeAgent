#!/usr/bin/env python3
"""Mission Control : les tâches finies, la plus récente d'abord.

La page En direct montre ce qui vient de se passer ; cette fiche
(``#/objet/file/finies``) garde l'historique : une ligne par tâche finie,
avec son heure, son état, sa durée, ce qui l'a lancée et ce qu'elle a
rendu en une phrase. Un clic ouvre la fiche de la tâche.

Une relève qui revient toutes les deux minutes ferait des centaines de
lignes par jour. Les tâches de routine (lancées par un déclencheur ou par
une autre tâche, sans réponse d'un modèle) font donc une seule ligne par
invocation, par état et par erreur : « Relever les messages · 634 fois »,
placée à l'heure de la plus récente, qu'elle ouvre. Une tâche lancée par
un bouton, ou qui a rendu une réponse, garde toujours sa ligne.

Ce module donne aussi trois petites phrases que la fiche d'une tâche
réutilise : ce qui l'a lancée, sa durée, et l'extrait de sa réponse.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from serge.mc.proj_objet_base import _champs

ETATS_TACHE = {
    'ready': 'Prête',
    'running': 'En cours',
    'done': 'Terminée',
    'failed': 'Échouée',
    'cancelled': 'Annulée',
    'blocked': 'Attend Julien',
}

# Combien de tâches on relit, et combien de lignes on montre au plus.
LUES = 2000
LIGNES_MAX = 200
EXTRAIT_MAX = 200


def duree(debut: str, fin: str) -> str:
    """« 24 s », « 3 min 26 s », « 1 h 05 min » ; ``''`` sans les deux
    heures."""
    try:
        secondes = int(
            (
                datetime.fromisoformat(fin) - datetime.fromisoformat(debut)
            ).total_seconds()
        )
    except ValueError:
        return ''
    if secondes < 0:
        return ''
    if secondes < 1:
        return 'moins d’une seconde'
    if secondes < 60:
        return f'{secondes} s'
    minutes, secondes = divmod(secondes, 60)
    if minutes < 60:
        return f'{minutes} min {secondes:02d} s'
    heures, minutes = divmod(minutes, 60)
    return f'{heures} h {minutes:02d} min'


def extrait(answer_json: str) -> str:
    """Ce qu'une tâche a rendu, en une phrase : le plus long texte de sa
    réponse (son compte rendu, son résumé), coupé."""
    try:
        reponse = json.loads(answer_json or '{}')
    except ValueError:
        return ''
    if not isinstance(reponse, dict):
        return ''
    textes = [v.strip() for v in reponse.values() if isinstance(v, str)]
    if not textes:
        return ''
    texte = ' '.join(max(textes, key=len).split())
    if len(texte) <= EXTRAIT_MAX:
        return texte
    return texte[: EXTRAIT_MAX - 1].rstrip() + '…'


def _milliers(nombre: int) -> str:
    """« 2 000 » : les milliers séparés, à la française."""
    return f'{nombre:,}'.replace(',', '\u202f')


def _titres(conn: sqlite3.Connection, table: str) -> dict[str, str]:
    return {
        str(ident): str(titre or ident)
        for ident, titre in conn.execute(f'SELECT id, title FROM {table}')
    }


class Origines:
    """Ce qui a lancé une tâche, dit en français : un bouton, un
    déclencheur, la tâche d'avant (un lien), ou « Repartir d'ici »."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.declencheurs = _titres(conn, 'triggers')
        self.liens = _titres(conn, 'links')

    def court(self, origin: str, ref: str) -> str:
        """Pour une colonne : « bouton », « déclencheur »…"""
        if origin == 'button':
            return 'bouton'
        if origin == 'trigger':
            return 'déclencheur'
        if origin == 'link':
            return 'tâche d’avant'
        if ref.startswith('reparti:'):
            return '« Repartir d’ici »'
        return '—'

    def long(self, origin: str, ref: str) -> str:
        """Pour la fiche : « le bouton « Fouiller un réseau » »."""
        ident = ref.split(':', 1)[0]
        if origin == 'button':
            return f'le bouton « {self.declencheurs.get(ident, ident)} »'
        if origin == 'trigger':
            return f'le déclencheur « {self.declencheurs.get(ident, ident)} »'
        if origin == 'link':
            return (
                'la tâche d’avant, par le lien'
                f' « {self.liens.get(ident, ident)} »'
            )
        if ref.startswith('reparti:'):
            return '« Repartir d’ici », sur une autre tâche'
        return ref or '—'


def routine(origin: str, a_rendu: object) -> bool:
    """Une tâche de routine : personne ne l'a lancée d'un bouton, et aucun
    modèle n'a rien rendu. Les routines pareilles font une seule ligne."""
    return origin != 'button' and not a_rendu


def _groupes(rows: list[Any]) -> list[list[Any]]:
    """Range les tâches en lignes, la plus récente d'abord : les routines
    pareilles (même invocation, même état, même erreur) ensemble, à la
    place de la plus récente ; les autres chacune à part."""
    groupes: list[list[Any]] = []
    ouverts: dict[tuple[Any, ...], list[Any]] = {}
    for row in rows:
        if not routine(str(row[3]), row[8]):
            groupes.append([row])
            continue
        cle = (row[1], row[2], row[7])
        if cle not in ouverts:
            ouverts[cle] = []
            groupes.append(ouverts[cle])
        ouverts[cle].append(row)
    return groupes


def project_taches_finies(conn: sqlite3.Connection) -> dict[str, Any]:
    """La fiche « Tâches finies » : un tableau, la plus récente d'abord."""
    # id, titre, état, origine, sa référence, commencée, finie, erreur,
    # a rendu une réponse, créée
    rows = conn.execute(
        "SELECT t.id, COALESCE(NULLIF(i.title, ''), t.invocation_id),"
        ' t.status, t.origin, t.origin_ref, t.started_at, t.finished_at,'
        " t.last_error, t.answer_json<>'', t.created_at FROM tasks t"
        ' LEFT JOIN invocations i ON i.id=t.invocation_id'
        " WHERE t.status IN ('done', 'failed', 'cancelled')"
        ' ORDER BY t.rowid DESC LIMIT ?',
        (LUES,),
    ).fetchall()
    rows.sort(key=lambda r: str(r[6] or r[9]), reverse=True)
    origines = Origines(conn)
    lignes = []
    for groupe in _groupes(rows)[:LIGNES_MAX]:
        tete = groupe[0]
        titre = str(tete[1])
        rendu = str(tete[7] or '')
        if tete[8]:
            reponse = conn.execute(
                'SELECT answer_json FROM tasks WHERE id=?', (tete[0],)
            ).fetchone()
            rendu = extrait(str(reponse[0])) or rendu
        temps = duree(str(tete[5]), str(tete[6]))
        if len(groupe) > 1:
            # La ligne d'un groupe : combien de fois, la plus récente.
            titre = f'{titre} · {_milliers(len(groupe))} fois'
            temps = ''
        lignes.append(
            {
                'type': 'task',
                'id': str(tete[0]),
                'cellules': [
                    str(tete[6] or tete[9] or '—'),
                    titre,
                    ETATS_TACHE.get(str(tete[2]), str(tete[2])),
                    temps or '—',
                    origines.court(str(tete[3]), str(tete[4])),
                    rendu or '—',
                ],
            }
        )
    compte = {
        etat: sum(1 for r in rows if r[2] == etat) for etat in ETATS_TACHE
    }
    return {
        'type': 'file',
        'id': 'finies',
        'titre': 'Tâches finies',
        'pourquoi': (
            'Les tâches finies, la plus récente d’abord, parmi les'
            f' {_milliers(LUES)} dernières. Une tâche lancée par un bouton,'
            ' ou dont un modèle a rendu la réponse, a sa ligne. Les tâches'
            ' de routine pareilles (une relève qui revient toutes les deux'
            ' minutes) font une seule ligne, qui dit combien de fois, à'
            ' l’heure de la plus récente. Un clic ouvre la fiche de la'
            ' tâche : ce qu’elle a rendu, son journal, ses appels d’outils.'
        ),
        'champs': _champs(
            [
                ('Terminées', compte['done']),
                ('Échouées', compte['failed']),
                ('Annulées', compte['cancelled']),
                (
                    'Depuis',
                    str(rows[-1][6] or rows[-1][9]) if rows else '—',
                ),
            ]
        ),
        'cadres': [
            {
                'titre': 'Les files',
                'liens': [
                    {
                        'type': 'file',
                        'id': 'canon',
                        'titre': 'Les tâches en cours et prêtes',
                    }
                ],
            }
        ],
        'tableau': {
            'colonnes': [
                'Finie',
                'Tâche',
                'État',
                'Durée',
                'Lancée par',
                'Ce qu’elle a rendu',
            ],
            'lignes': lignes,
        },
        'enfants': [],
        'preuve': '',
    }
