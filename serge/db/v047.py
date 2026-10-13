#!/usr/bin/env python3
"""Migration v47 : appeler une API décrite en base (lot 10, Q56 et Q91).

Un connecteur n'est pas du code : c'est la description d'un service.

- ``api_services`` : un service (Stripe en mode test, Stripe en vrai
  mode…) : son adresse, comment s'authentifier (``bearer`` ou rien), le
  fichier de secret à lire dans les secrets de l'instance (son nom, jamais
  sa valeur), et le format du corps des requêtes (``form`` ou ``json``).
- ``api_endpoints`` : un point d'entrée, qui est un outil (``tool_id``) :
  sa méthode, son chemin (``/v1/prices/{id}``), le service par défaut.
- ``api_endpoint_params`` : les paramètres permis d'un point d'entrée. Un
  paramètre figé en base sur l'invocation (l'identifiant du business sur
  un prix Stripe) ne peut pas être choisi par le modèle.
"""

from __future__ import annotations

import sqlite3

SCRIPT = """
CREATE TABLE IF NOT EXISTS api_services (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL,
    auth TEXT NOT NULL DEFAULT 'bearer' CHECK (auth IN ('bearer', 'none')),
    secret_file TEXT NOT NULL DEFAULT '',
    body TEXT NOT NULL DEFAULT 'json' CHECK (body IN ('form', 'json')),
    doc_md TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS api_endpoints (
    tool_id TEXT PRIMARY KEY,
    service_id TEXT NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('GET', 'POST', 'PUT', 'DELETE')),
    path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS api_endpoint_params (
    tool_id TEXT NOT NULL,
    name TEXT NOT NULL,
    type TEXT NOT NULL DEFAULT 'text'
        CHECK (type IN ('text', 'number', 'bool', 'json')),
    required INTEGER NOT NULL DEFAULT 0 CHECK (required IN (0, 1)),
    description TEXT NOT NULL DEFAULT '',
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tool_id, name)
);
"""


def apply_v047(connection: sqlite3.Connection) -> None:
    """Crée les services, leurs points d'entrée et leurs paramètres."""
    connection.executescript(SCRIPT)
