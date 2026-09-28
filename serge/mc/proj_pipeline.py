#!/usr/bin/env python3
"""Page Pipeline : la vue d'ensemble du pipeline, tel qu'il est en base.

Les capacités du code, les outils, les liens (avec ce qui attend un clic),
les déclencheurs, ce que les invocations voient de chaque table, le modèle
derrière chaque niveau et le texte « Qui est Serge ». Les deux derniers se
modifient sur la page ; le reste s'ouvre en fiche.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.interpreter.run import resolve_model
from serge.mc.proj_lien import MODES
from serge.mc.proj_llm import EVENEMENTS, NIVEAUX


def _titres(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(i): str(t or i)
        for i, t in conn.execute(
            'SELECT id, title FROM invocations'
        ).fetchall()
    }


def _capacites(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {
            'id': str(ident),
            'titre': str(titre),
            'disponible': bool(dispo),
            'code': str(code or ''),
            'outils': int(outils),
        }
        for ident, titre, dispo, code, outils in conn.execute(
            'SELECT c.id, c.title, c.available, c.code_path,'
            ' (SELECT COUNT(*) FROM tools t WHERE t.capability_id=c.id)'
            ' FROM capabilities c ORDER BY c.id'
        ).fetchall()
    ]


def _outils(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [
        {
            'id': str(ident),
            'titre': str(titre or ident),
            'capacite': str(capacite),
            'utilise_par': 'toutes les invocations LLM'
            if partout
            else f'{int(nombre)} invocation(s)',
        }
        for ident, titre, capacite, partout, nombre in conn.execute(
            'SELECT t.id, t.titre, t.capability_id, t.montre_partout,'
            ' (SELECT COUNT(DISTINCT it.invocation_id) FROM invocation_tools'
            ' it WHERE it.tool_id=t.id) FROM tools t ORDER BY t.id'
        ).fetchall()
    ]


def _liens(
    conn: sqlite3.Connection, titres: Mapping[str, str]
) -> list[dict[str, Any]]:
    out = []
    for (
        ident,
        titre,
        de,
        vers,
        mode,
        auto,
        allume,
        attente,
        passes,
    ) in conn.execute(
        'SELECT l.id, l.title, l.from_invocation_id, l.to_invocation_id,'
        ' l.mode, l.auto, l.enabled,'
        ' (SELECT COUNT(*) FROM link_passages p WHERE p.link_id=l.id'
        " AND p.passed_at=''),"
        ' (SELECT COUNT(*) FROM link_passages p WHERE p.link_id=l.id'
        " AND p.passed_at<>'')"
        " FROM links l WHERE l.deleted_at='' ORDER BY l.id"
    ).fetchall():
        de_titre = titres.get(str(de), str(de))
        out.append(
            {
                'id': str(ident),
                'titre': str(titre or ident),
                'chemin': f'{de_titre} → {titres.get(str(vers), str(vers))}',
                'quand': MODES.get(str(mode), str(mode)).format(de=de_titre),
                'passage': 'automatique' if auto else 'à la main',
                'allume': bool(allume),
                'attente': int(attente),
                'passes': int(passes),
            }
        )
    return out


def _declencheurs(
    conn: sqlite3.Connection, titres: Mapping[str, str]
) -> list[dict[str, Any]]:
    return [
        {
            'id': str(ident),
            'titre': str(titre or ident),
            'invocation': str(inv),
            'invocation_titre': titres.get(str(inv), str(inv)),
            'quand': EVENEMENTS.get(str(event), str(event)).format(
                table=table, every=every, at=at, jours=days or 'tous les jours'
            ),
            'allume': bool(allume),
        }
        for ident, titre, inv, event, table, every, at, days, allume in (
            conn.execute(
                'SELECT id, title, invocation_id, event, table_name,'
                ' every_minutes, at_time, at_days, enabled FROM triggers'
                " WHERE deleted_at='' ORDER BY id"
            ).fetchall()
        )
    ]


def _tables(conn: sqlite3.Connection) -> list[dict[str, str]]:
    out = []
    for table, titre, ordre in conn.execute(
        'SELECT table_name, title, order_column FROM table_views'
        ' ORDER BY table_name'
    ).fetchall():
        colonnes = conn.execute(
            'SELECT column_name, short FROM table_view_columns'
            ' WHERE table_name=? ORDER BY position, column_name',
            (table,),
        ).fetchall()
        out.append(
            {
                'table': str(table),
                'titre': str(titre or table),
                'ordre': str(ordre or '—'),
                'courte': ', '.join(str(c) for c, s in colonnes if s),
                'lisibles': ', '.join(str(c) for c, _ in colonnes),
            }
        )
    return out


def _modeles(conn: sqlite3.Connection) -> list[dict[str, str]]:
    out = []
    for tier, model in conn.execute(
        "SELECT tier, model FROM llm_models ORDER BY CASE tier WHEN 'fast'"
        " THEN 0 WHEN 'mid' THEN 1 ELSE 2 END"
    ).fetchall():
        out.append(
            {
                'tier': str(tier),
                'libelle': NIVEAUX.get(str(tier), str(tier)),
                'model': str(model or ''),
                'effectif': resolve_model(conn, str(tier))[0],
            }
        )
    return out


def project_pipeline(
    conn: sqlite3.Connection, policy: Mapping[str, Any], now_iso: str
) -> dict[str, Any]:
    """Tout le pipeline décrit en base, pour la page Pipeline."""
    del policy, now_iso
    titres = _titres(conn)
    texte = conn.execute(
        "SELECT body FROM serge_texts WHERE id='presentation'"
    ).fetchone()
    return {
        'capacites': _capacites(conn),
        'outils': _outils(conn),
        'liens': _liens(conn, titres),
        'declencheurs': _declencheurs(conn, titres),
        'tables': _tables(conn),
        'modeles': _modeles(conn),
        'presentation': str(texte[0]) if texte else '',
    }
