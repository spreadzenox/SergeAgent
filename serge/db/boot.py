#!/usr/bin/env python3
"""Ouvrir la base : migrations, puis remplissage de départ."""

from __future__ import annotations

import sqlite3


def init_schema(connection: sqlite3.Connection) -> None:
    """Applique les migrations manquantes, puis remplit ce qui manque.

    Le remplissage n'écrase jamais un réglage déjà en base : il ajoute les
    étapes, les canaux, les capacités du code, le pipeline de départ
    (``config/pipeline.yaml``), les réglages généraux
    (``config/policy.yaml``) et les types de tickets
    (``config/ticket-types.yaml``), puis calcule les empreintes du code.

    Args:
        connection: Connexion (commit par l'appelant).
    """
    from serge.canaux import ensure_canaux
    from serge.capabilities import ensure_capabilities
    from serge.comptes import ensure_account_columns
    from serge.db.migrate import apply_pending
    from serge.etapes import ensure_pipeline_steps
    from serge.objet_sha import poser_shas
    from serge.pipeline_seed import ensure_pipeline
    from serge.policy_store import ensure_policy
    from serge.tickets.types import ensure_ticket_types

    apply_pending(connection)
    ensure_account_columns(connection)
    ensure_pipeline_steps(connection)
    ensure_canaux(connection)
    ensure_capabilities(connection)
    ensure_pipeline(connection)
    ensure_policy(connection)
    ensure_ticket_types(connection)
    poser_shas(connection)
