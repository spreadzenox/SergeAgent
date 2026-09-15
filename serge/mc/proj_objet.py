#!/usr/bin/env python3
"""Fiches objet : une table / un enum = une brique cliquable."""

from __future__ import annotations

import sqlite3
from typing import Any


def project_objet(
    conn: sqlite3.Connection, typ: str, ident: str
) -> dict[str, Any] | None:
    """Fiche objet {type, id, titre, champs, enfants, preuve} ou None."""
    if typ == 'file':
        from serge.db.store import utcnow
        from serge.mc.proj_live import project_file_detail

        return project_file_detail(conn, utcnow())
    if typ in ('llm', 'llm_usage', 'contexte', 'ecoute', 'outil', 'notion'):
        from serge.mc.proj_llm import (
            project_contexte,
            project_ecoute,
            project_llm,
            project_llm_usage,
            project_notion,
            project_outil,
        )

        return {
            'llm': project_llm,
            'llm_usage': project_llm_usage,
            'contexte': project_contexte,
            'ecoute': project_ecoute,
            'outil': project_outil,
            'notion': project_notion,
        }[typ](conn, ident)
    if typ == 'identite':
        from serge.mc.proj_identite import project_identite

        return project_identite(ident)
    if typ == 'tech':
        from serge.tech_registre import fiche_tech

        return fiche_tech(conn, ident)
    if typ == 'canal':
        from serge.canaux import fiche_canal

        return fiche_canal(conn, ident)
    if typ == 'etape':
        from serge.mc.proj_etape import project_etape

        return project_etape(conn, ident)
    if typ in ('sqlite', 'table'):
        from serge.mc.proj_sqlite import project_sqlite, project_table

        if typ == 'sqlite':
            return project_sqlite(conn, ident)
        return project_table(conn, ident)
    from serge.mc.proj_faits import project_fait_pipe
    from serge.mc.proj_traces import project_fait_trace

    return project_fait_pipe(conn, typ, ident) or project_fait_trace(
        conn, typ, ident
    )
