#!/usr/bin/env python3
"""Fiche d'un lien : ce qui est passé, ce qui attend, et les boutons.

Un lien passe la main d'une invocation à la suivante. Réglé « à la main »,
il note chaque passage et attend que Julien clique sur « Passer à la
suite ». L'interrupteur « passage automatique » ne vaut que pour les
passages suivants. Tout est lu en base.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.mc.proj_llm import SOURCES

MODES = {
    'on_finish': 'à la fin de chaque passage de « {de} »',
    'per_row': 'pour chaque ligne écrite par « {de} »',
}


def _titre(conn: sqlite3.Connection, invocation_id: str) -> str:
    row = conn.execute(
        'SELECT title FROM invocations WHERE id=?', (invocation_id,)
    ).fetchone()
    return str(row[0]) if row and row[0] else invocation_id


def _parametres(conn: sqlite3.Connection, link_id: str, ref: str) -> str:
    return ', '.join(
        f'{name} = {value}'
        for name, value in conn.execute(
            'SELECT name, value FROM link_passage_params'
            ' WHERE link_id=? AND source_ref=? ORDER BY name',
            (link_id, ref),
        ).fetchall()
    )


def attente(conn: sqlite3.Connection, link_id: str) -> int:
    """Le nombre de passages qui attendent un clic."""
    row = conn.execute(
        "SELECT COUNT(*) FROM link_passages WHERE link_id=? AND passed_at=''",
        (link_id,),
    ).fetchone()
    return int(row[0])


def project_lien(
    conn: sqlite3.Connection, ident: str
) -> dict[str, Any] | None:
    """La fiche d'un lien, ou ``None`` s'il n'existe pas."""
    row = conn.execute(
        'SELECT title, from_invocation_id, to_invocation_id, mode, auto,'
        " enabled FROM links WHERE id=? AND deleted_at=''",
        (ident,),
    ).fetchone()
    if row is None:
        return None
    titre, de, vers, mode, auto, allume = row
    params = ' ; '.join(
        f'{name} ← {SOURCES.get(str(source), "{}").format(value)}'
        for name, source, value in conn.execute(
            'SELECT param_name, source, value FROM link_params'
            ' WHERE link_id=? ORDER BY param_name',
            (ident,),
        ).fetchall()
    )
    champs = [
        {'k': 'De', 'v': _titre(conn, str(de))},
        {'k': 'Vers', 'v': _titre(conn, str(vers))},
        {
            'k': 'Quand',
            'v': MODES.get(str(mode), str(mode)).format(
                de=_titre(conn, str(de))
            ),
        },
        {'k': 'Paramètres transmis', 'v': params or 'aucun'},
        {
            'k': 'Passage automatique',
            'v': 'oui' if auto else 'non : chaque passage attend un clic',
        },
        {'k': 'Allumé', 'v': 'oui' if allume else 'non'},
    ]
    attendus = conn.execute(
        'SELECT source_ref, created_at FROM link_passages'
        " WHERE link_id=? AND passed_at='' ORDER BY created_at, source_ref",
        (ident,),
    ).fetchall()
    passes = conn.execute(
        'SELECT source_ref, passed_at, task_id FROM link_passages'
        " WHERE link_id=? AND passed_at<>''"
        ' ORDER BY passed_at DESC, source_ref LIMIT 20',
        (ident,),
    ).fetchall()
    bascule = {
        'libelle': 'Passer à la main' if auto else 'Passer en automatique',
        'route': '/owner/api/lien/auto',
        'charge': {'link_id': ident, 'auto': not auto},
        'confirmer': (
            'Les prochains passages attendront un clic sur « Passer à la'
            ' suite ».'
            if auto
            else 'Les prochains passages lanceront l’invocation suivante'
            ' tout seuls. Ce qui attend déjà un clic continue d’attendre.'
        ),
    }
    return {
        'type': 'lien',
        'id': ident,
        'titre': str(titre or ident),
        'pourquoi': (
            'Un lien passe la main d’une invocation à la suivante, avec des'
            ' paramètres. Un même résultat ne passe jamais deux fois.'
        ),
        'actions': [bascule],
        'champs': champs,
        'cadres': [
            {
                'titre': 'Les deux invocations',
                'liens': [
                    {
                        'type': 'llm',
                        'id': str(de),
                        'titre': _titre(conn, str(de)),
                    },
                    {
                        'type': 'llm',
                        'id': str(vers),
                        'titre': _titre(conn, str(vers)),
                    },
                ],
            },
            {
                'titre': 'Ce qui attend un clic',
                'texte': (
                    f'{len(attendus)} passage(s) en attente.'
                    if attendus
                    else 'Rien n’attend.'
                ),
                'champs': [
                    {
                        'k': str(ref),
                        'v': f'depuis {quand}'
                        + (
                            f' ; {_parametres(conn, ident, str(ref))}'
                            if _parametres(conn, ident, str(ref))
                            else ''
                        ),
                    }
                    for ref, quand in attendus
                ],
                'actions': [
                    {
                        'libelle': f'Passer à la suite : {ref}',
                        'route': '/owner/api/lien/passer',
                        'charge': {'link_id': ident, 'source_ref': str(ref)},
                    }
                    for ref, _quand in attendus
                ],
            },
        ],
        'tableau': {
            'titre': 'Déjà passé (les 20 derniers)',
            'colonnes': ['Quand', 'Ce qui est passé', 'Tâche'],
            'lignes': [
                {
                    'cellules': [str(quand), str(ref), str(task or '—')],
                    'type': 'task' if task else '',
                    'id': str(task or ''),
                }
                for ref, quand, task in passes
            ],
        },
        'enfants': [],
        'preuve': '',
    }
