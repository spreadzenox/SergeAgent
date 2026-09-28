#!/usr/bin/env python3
"""Fiche d'une invocation : ce qu'elle voit pour comparer, et ses leçons.

Tout est lu en base, avec les mêmes fonctions que l'interpréteur : Julien
voit exactement ce que l'invocation recevra au prochain appel. Chaque
table peut être retirée, remise ou ajoutée d'un clic.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.interpreter.intro import lessons_for
from serge.interpreter.seen import compare_tables, view_columns

RAISONS = {
    'ecrit': 'elle y écrit',
    'ajoutee': 'ajoutée à la main',
    'retiree': 'retirée à la main : elle y écrit, mais ne la voit pas',
}

PORTEES = {
    'invocation': 'Pour elle',
    'etape': 'Pour son étape',
    'global': 'Pour tout Serge',
}

ROUTE = '/owner/api/invocation/comparer'


def _action(ident: str, table: str, voir: bool, libelle: str) -> dict:
    return {
        'libelle': libelle,
        'route': ROUTE,
        'charge': {'invocation_id': ident, 'table': table, 'voir': voir},
    }


def cadres_vues(
    conn: sqlite3.Connection, ident: str, step_id: str, max_rows: int
) -> list[dict[str, Any]]:
    """Le cadre des tables à comparer, et celui de ses leçons."""
    titres = {
        str(t): str(titre or t)
        for t, titre in conn.execute(
            'SELECT table_name, title FROM table_views ORDER BY table_name'
        ).fetchall()
    }
    champs: list[dict[str, str]] = []
    actions: list[dict[str, Any]] = []
    vues = compare_tables(conn, ident)
    for table, raison in vues:
        colonnes = ', '.join(view_columns(conn, table, short=True))
        champs.append(
            {
                'k': titres[table],
                'v': f'{colonnes or "aucune colonne courte"} — {RAISONS[raison]}',
            }
        )
        if raison == 'retiree':
            actions.append(
                _action(ident, table, True, f'Remettre « {titres[table]} »')
            )
        else:
            actions.append(
                _action(ident, table, False, f'Retirer « {titres[table]} »')
            )
    deja = {table for table, _ in vues}
    for table, titre in titres.items():
        if table not in deja:
            actions.append(_action(ident, table, True, f'Ajouter « {titre} »'))
    lecons, total = lessons_for(conn, ident, step_id, max_rows)
    cadre_lecons: dict[str, Any] = {
        'titre': 'Ses leçons (données d’office)',
        'texte': (
            f'{total} leçon(s), les plus fiables d’abord : celles rattachées'
            ' à elle, puis à son étape, puis à tout Serge.'
            if total
            else 'Aucune leçon pour elle, son étape ou tout Serge.'
        ),
        'champs': [
            {'k': PORTEES[portee], 'v': f'{enonce} (fiabilité {fiab:.1f})'}
            for enonce, fiab, portee in lecons
        ],
    }
    return [
        {
            'titre': 'Ce qu’elle voit pour comparer (version courte)',
            'texte': (
                'Donnée d’office : les lignes les plus récentes d’abord, au'
                f' plus {max_rows} par table. Avec « Lire les tables que je'
                ' vois », elle lit le reste de ces tables seulement, toutes'
                ' colonnes lisibles.'
            ),
            'champs': champs or [{'k': '—', 'v': 'Aucune table.'}],
            'actions': actions,
        },
        cadre_lecons,
    ]


def changer_comparaison(
    conn: sqlite3.Connection, ident: str, table: str, voir: bool, qui: str
) -> bool:
    """Ajoute, retire ou remet une table à comparer ; ``False`` si refusé.

    Une table où elle écrit est vue par défaut : la remettre efface
    l'ajustement. Seule une table décrite (``table_views``) peut être vue.
    """
    from serge.horloge import iso_utc

    if (
        not conn.execute(
            'SELECT 1 FROM table_views WHERE table_name=?', (table,)
        ).fetchone()
        or not conn.execute(
            "SELECT 1 FROM invocations WHERE id=? AND deleted_at=''", (ident,)
        ).fetchone()
    ):
        return False
    ecrit = conn.execute(
        'SELECT 1 FROM invocation_writes WHERE invocation_id=?'
        ' AND table_name=?',
        (ident, table),
    ).fetchone()
    if voir == bool(ecrit):
        conn.execute(
            'DELETE FROM invocation_compare_tables WHERE invocation_id=?'
            ' AND table_name=?',
            (ident, table),
        )
    else:
        conn.execute(
            'INSERT OR REPLACE INTO invocation_compare_tables(invocation_id,'
            ' table_name, included, updated_at, updated_by)'
            ' VALUES(?,?,?,?,?)',
            (ident, table, int(voir), iso_utc(), qui),
        )
    return True
