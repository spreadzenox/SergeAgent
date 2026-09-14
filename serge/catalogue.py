#!/usr/bin/env python3
"""Graphe d’architecture en canon : présent et relié sur toute instance."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.etapes import ETAPE_IDS, etats_etapes
from serge.llm_registre import POINT_LOCKS
from serge.mc.libelles import LLM_ETAPE
from serge.outils import SEED as TOOL_SEED
from serge.tech_registre import SEED as TECH_SEED
from serge.tech_registre import tech_par_etape

HORS_EPINE = frozenset({'policy'})


class CatalogueError(ValueError):
    """Le catalogue d’architecture est incomplet ou mal relié."""


def etapes_permises() -> frozenset[str]:
    """Ids d’étape valides pour un rattachement."""
    return frozenset(ETAPE_IDS) | HORS_EPINE


def objets_de_etape(
    conn: sqlite3.Connection, etape_id: str
) -> dict[str, list[dict[str, Any]]]:
    """Objets d’un sac : invocations LLM, techniques, kinds typiques.

    Args:
        conn: Canon.
        etape_id: Id d’étape (épine).

    Returns:
        ``{llm, tech, kinds}``.
    """
    llm_rows = conn.execute(
        'SELECT id, titre FROM llm_points WHERE etape_id=? ORDER BY id',
        (etape_id,),
    ).fetchall()
    spec = etats_etapes(conn).get(etape_id) or {}
    return {
        'llm': [{'id': str(r[0]), 'titre': str(r[1])} for r in llm_rows],
        'tech': tech_par_etape(conn, etape_id),
        'kinds': list(spec.get('kinds') or []),
    }


def verifier_catalogue(conn: sqlite3.Connection) -> None:
    """Refuse un canon dont le graphe d’architecture manque.

    Args:
        conn: Canon déjà semé.

    Raises:
        CatalogueError: Objet manquant ou lien cassé.
    """
    erreurs: list[str] = []
    steps = {
        str(r[0])
        for r in conn.execute('SELECT id FROM pipeline_steps').fetchall()
    }
    for ident in ETAPE_IDS:
        if ident not in steps:
            erreurs.append(f'étape absente : {ident}')
    points = {
        str(r[0]): str(r[1] or '')
        for r in conn.execute('SELECT id, etape_id FROM llm_points')
    }
    for ident in POINT_LOCKS:
        if ident not in points:
            erreurs.append(f'invocation LLM absente : {ident}')
        else:
            etape = points[ident]
            attendu = LLM_ETAPE.get(ident, '')
            if etape != attendu:
                erreurs.append(f'{ident} : etape_id {etape!r} ≠ {attendu!r}')
            if etape not in etapes_permises():
                erreurs.append(f'{ident} : étape inconnue {etape!r}')
    tools = {
        str(r[0]) for r in conn.execute('SELECT id FROM tools').fetchall()
    }
    for row in TOOL_SEED:
        if row[0] not in tools:
            erreurs.append(f'outil absent : {row[0]}')
    techs = {
        str(r[0]): str(r[1] or '')
        for r in conn.execute('SELECT id, etape_id FROM tech_invocations')
    }
    for row in TECH_SEED:
        if row[0] not in techs:
            erreurs.append(f'invocation tech absente : {row[0]}')
        elif techs[row[0]] != row[1]:
            erreurs.append(f'{row[0]} : etape_id mal relié')
        elif row[1] not in ETAPE_IDS:
            erreurs.append(f'{row[0]} : étape {row[1]!r} hors épine')
    orphelins = conn.execute(
        'SELECT point_id, tool_id FROM llm_point_tools'
        ' WHERE point_id NOT IN (SELECT id FROM llm_points)'
        ' OR tool_id NOT IN (SELECT id FROM tools)'
    ).fetchall()
    for point_id, tool_id in orphelins:
        erreurs.append(f'jonction orpheline : {point_id} → {tool_id}')
    if erreurs:
        raise CatalogueError(' ; '.join(erreurs[:12]))
