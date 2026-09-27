#!/usr/bin/env python3
"""Graphe d’architecture en canon : présent et relié sur toute instance."""

from __future__ import annotations

import sqlite3
from typing import Any

from serge.canaux import JONCTIONS as CANAL_JONCTIONS
from serge.canaux import SEED as CANAL_SEED
from serge.etape_fiches import DEBITS, LIENS
from serge.etapes import ETAPE_IDS, etats_etapes
from serge.llm_registre import POINT_PATHS
from serge.mc.libelles import LLM_ETAPE
from serge.outils import SEED as TOOL_SEED
from serge.tech_registre import SEED as TECH_SEED
from serge.tech_registre import tech_par_etape

HORS_EPINE = frozenset({'policy'})


def _canaux_etape(
    conn: sqlite3.Connection, etape_id: str
) -> list[dict[str, Any]]:
    """Canaux d’une étape (via ses briques)."""
    from serge.canaux import canaux_de_etape

    return canaux_de_etape(conn, etape_id)


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
        ``{llm, tech, kinds, canaux}``.
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
        'canaux': _canaux_etape(conn, etape_id),
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
    for ident in POINT_PATHS:
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
    liens = {
        str(r[0]): (str(r[1]), str(r[2]), str(r[3]))
        for r in conn.execute('SELECT id, de, vers, debit FROM etape_liens')
    }
    for ident, de, vers, _libelle, debit, _rang in LIENS:
        if ident not in liens:
            erreurs.append(f'lien absent : {ident}')
            continue
        got_de, got_vers, got_debit = liens[ident]
        if (got_de, got_vers) != (de, vers):
            erreurs.append(f'{ident} : extrémités {got_de}→{got_vers}')
        if got_debit != debit or debit not in DEBITS:
            erreurs.append(f'{ident} : débit {got_debit!r}')
        if de not in ETAPE_IDS or vers not in ETAPE_IDS:
            erreurs.append(f'{ident} : étape hors épine')
    canaux = {
        str(r[0]) for r in conn.execute('SELECT id FROM canaux').fetchall()
    }
    for row in CANAL_SEED:
        if row[0] not in canaux:
            erreurs.append(f'canal absent : {row[0]}')
    attendu_j = {(c, k, b) for c, k, b in CANAL_JONCTIONS}
    got_j = {
        (str(r[0]), str(r[1]), str(r[2]))
        for r in conn.execute(
            'SELECT canal_id, brique_kind, brique_id FROM brique_canaux'
        )
    }
    for item in sorted(got_j - attendu_j):
        erreurs.append(f'jonction canal en trop : {item[0]} → {item[2]}')
    orphelins_c = conn.execute(
        'SELECT canal_id, brique_kind, brique_id FROM brique_canaux'
        ' WHERE canal_id NOT IN (SELECT id FROM canaux)'
        " OR (brique_kind='llm' AND brique_id NOT IN"
        ' (SELECT id FROM llm_points))'
        " OR (brique_kind='tech' AND brique_id NOT IN"
        ' (SELECT id FROM tech_invocations))'
    ).fetchall()
    for canal_id, kind, brique_id in orphelins_c:
        erreurs.append(
            f'jonction canal orpheline : {canal_id} → {kind}.{brique_id}'
        )
    if erreurs:
        raise CatalogueError(' ; '.join(erreurs[:12]))
