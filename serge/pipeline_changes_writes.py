#!/usr/bin/env python3
"""Ajouter une règle d'écriture à une invocation déjà en base, une seule
fois.

Une sorte de modification de la section ``changes`` de
``config/pipeline.yaml`` (voir ``serge/pipeline_changes.py``) :
``add_writes``, avec ``invocation``. Chaque règle dit son rang
(``position``) dans les écritures de l'invocation, le même que dans
``pipeline.yaml`` : un lien « par ligne écrite » désigne une écriture par
ce rang. Exemple : « Concevoir le produit » écrit aussi les offres du
produit, au rang 9.

Un rang déjà pris est gardé tel quel : sur une base neuve, l'écriture y
est déjà ; sur une instance où l'invocation a été changée à la main, on
ne touche à rien. Ces modifications passent avant la pose des liens.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from typing import Any

from serge.pipeline_changes_remove import invocation_absente
from serge.seed_base import PipelineSeedError, seed_write


def add_writes(conn: sqlite3.Connection, invocation: str, raw: Any) -> str:
    """Ajoute des règles d'écriture à une invocation déjà en base."""
    if not isinstance(raw, list) or not all(
        isinstance(w, Mapping) and isinstance(w.get('position'), int)
        for w in raw
    ):
        raise PipelineSeedError(
            'changes : add_writes, une liste de règles avec leur position'
        )
    if invocation_absente(conn, invocation):
        return 'objet absent'
    parts = []
    for write in raw:
        position = int(write['position'])
        if conn.execute(
            'SELECT 1 FROM invocation_writes WHERE invocation_id=?'
            ' AND position=?',
            (invocation, position),
        ).fetchone():
            parts.append(f'écriture {position} déjà là')
            continue
        seed_write(conn, invocation, position, write)
        parts.append(f'écriture {position} ajoutée ({write["table"]})')
    return ' ; '.join(parts)
