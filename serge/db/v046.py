#!/usr/bin/env python3
"""Migration v46 : concevoir, critiquer, construire, relire (lot 10, Q91).

- ``product_plans`` : une ligne par version d'un plan, pour un POC comme
  pour un produit fini (``kind`` = ``poc`` ou ``product``) : le plan de A
  à Z (Q34), les scénarios de test que suivent le relecteur et l'humain
  du ticket de test, le tour de critique, l'avis du critique et les
  consignes d'un humain. Statut : ``draft``, ``challenged``,
  ``validated``, ``to_fix``, ``refused``.
- ``plan_critiques`` : une ligne par remarque « à corriger » du critique.
  Un manque (« nouvelle capacité ») passe par l'outil « Demander une
  nouvelle capacité ».
- ``builds`` : une ligne par passage de construction : le compte rendu du
  constructeur, puis le verdict et les remarques du relecteur.
- Un paramètre de lien peut venir d'un champ de la réponse de
  l'invocation qui vient de finir (``link_params.source`` = ``field``) :
  exemple, le tour suivant rendu par « Compter les tours ».
"""

from __future__ import annotations

import sqlite3

from serge.db.contrainte import widen_check

SCRIPT = """
CREATE TABLE IF NOT EXISTS product_plans (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('poc', 'product')),
    round INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    hypothesis TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    prospects INTEGER NOT NULL DEFAULT 0,
    duration_days INTEGER NOT NULL DEFAULT 0,
    price TEXT NOT NULL DEFAULT '',
    followups TEXT NOT NULL DEFAULT '',
    deliverable TEXT NOT NULL DEFAULT '',
    plan TEXT NOT NULL DEFAULT '',
    scenarios TEXT NOT NULL DEFAULT '',
    challenge TEXT NOT NULL DEFAULT '',
    owner_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_product_plans_venture
    ON product_plans(venture_id, created_at);
CREATE TABLE IF NOT EXISTS plan_critiques (
    id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL,
    venture_id TEXT NOT NULL DEFAULT '',
    round INTEGER NOT NULL DEFAULT 1,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plan_critiques_plan
    ON plan_critiques(plan_id);
CREATE TABLE IF NOT EXISTS builds (
    id TEXT PRIMARY KEY,
    venture_id TEXT NOT NULL,
    deliverable TEXT NOT NULL DEFAULT '',
    pass INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'built',
    report TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL DEFAULT '',
    remarks TEXT NOT NULL DEFAULT '',
    review TEXT NOT NULL DEFAULT '',
    owner_notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_builds_venture
    ON builds(venture_id, created_at);
"""


def apply_v046(connection: sqlite3.Connection) -> None:
    """Crée les plans, leurs critiques et les passages de construction ;
    un paramètre de lien peut venir de la réponse."""
    connection.executescript(SCRIPT)
    widen_check(
        connection,
        'link_params',
        "('row', 'task', 'fixed', 'setting')",
        "('row', 'task', 'fixed', 'setting', 'field')",
    )
