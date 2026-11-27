#!/usr/bin/env python3
"""Migration v59 : les services externes gratuits branchés à un produit.

Un produit peut avoir besoin d'un service d'un autre site (une API de
cartes, de conversion de fichiers…), qui demande un compte et une clé
(décision Q118). ``product_services`` garde, par business, chaque service
demandé : son nom court, son adresse, à quoi il sert, où il en est, et sa
clé, chiffrée par la clé du coffre comme le mot de passe d'un compte web.

Les états : ``asked`` (demandé pendant la construction, un humain doit
dire oui), ``connecting`` (le compte et la clé sont en cours),
``connected`` (la clé est gardée), ``failed`` (pas pu, avec la raison),
``refused`` (un humain a dit non).

Exemple : le produit « Tournées » demande ``openrouteservice`` ; sa ligne
porte ``env_name = SERVICE_OPENROUTESERVICE_KEY``, la variable par
laquelle le produit lit sa clé, dans le chantier, en staging et en prod.
"""

from __future__ import annotations

import sqlite3


def apply_v059(connection: sqlite3.Connection) -> None:
    """Crée la table des services externes des produits."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS product_services (
            id TEXT PRIMARY KEY,
            venture_id TEXT NOT NULL,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            purpose TEXT NOT NULL DEFAULT '',
            env_name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'asked',
            reason TEXT NOT NULL DEFAULT '',
            free_plan TEXT NOT NULL DEFAULT '',
            key_enc TEXT NOT NULL DEFAULT '',
            task_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(venture_id, name)
        );
        """
    )
