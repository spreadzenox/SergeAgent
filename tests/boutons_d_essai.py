#!/usr/bin/env python3
"""Aide de test : des boutons qui lancent une brique à part.

Les essais de la page Système ont été remplacés par l'essai total (lot 12,
décision Q99) ; ces boutons ne sont plus dans le pipeline de départ. Les
tests d'une brique (le chantier, le navigateur, la publication, Stripe, le
captcha, l'étape 2, l'étape 5) s'en servent encore comme point d'entrée :
``poser`` les ajoute à la base du test, tels qu'ils étaient
(``boutons_d_essai.json``). Les business qu'ils créent sont de vrais
business, pas des essais.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from serge.pipeline_seed import seed_pipeline


def poser(conn: sqlite3.Connection) -> None:
    """Ajoute les boutons d'essai des briques à la base d'un test."""
    data = json.loads(
        (Path(__file__).parent / 'boutons_d_essai.json').read_text('utf-8')
    )
    seed_pipeline(conn, data)
    conn.commit()
