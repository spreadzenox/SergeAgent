#!/usr/bin/env python3
"""Boot canon : migrations puis semence catalogue (hors schema.py)."""

from __future__ import annotations

import sqlite3


def init_schema(connection: sqlite3.Connection) -> None:
    """Applique les migrations manquantes, puis sème le catalogue.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    from serge.canaux import ensure_canaux
    from serge.catalogue import verifier_catalogue
    from serge.comptes import ensure_account_columns
    from serge.db.migrate import apply_pending
    from serge.db_readers import ensure_db_readers
    from serge.etape_fiches import ensure_etape_liens
    from serge.etapes import ensure_pipeline_steps
    from serge.llm_registre import ensure_llm_points
    from serge.objet_sha import poser_shas
    from serge.outils import ensure_tools
    from serge.tech_registre import ensure_tech_invocations

    apply_pending(connection)
    ensure_account_columns(connection)
    ensure_pipeline_steps(connection)
    ensure_tools(connection)
    ensure_llm_points(connection)
    ensure_tech_invocations(connection)
    ensure_etape_liens(connection)
    ensure_canaux(connection)
    ensure_db_readers(connection)
    poser_shas(connection)
    verifier_catalogue(connection)
