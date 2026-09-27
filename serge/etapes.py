#!/usr/bin/env python3
"""Les 8 étapes de la chaîne, leur ordre et leur interrupteur.

Une étape coupée ne lance plus aucune de ses invocations : la file saute
les tâches dont l'invocation appartient à cette étape.
"""

from __future__ import annotations

import sqlite3
from typing import Any

# Les 8 étapes, dans l'ordre de la chaîne (id, rang).
STEPS: tuple[tuple[str, int], ...] = (
    ('pre_prospection', 0),
    ('conception_poc', 1),
    ('prospection_light', 2),
    ('choix_venture', 3),
    ('build_venture', 4),
    ('prospection_lourde', 5),
    ('collect_feedback', 6),
    ('caisse', 7),
)
ETAPE_IDS = tuple(ident for ident, _rang in STEPS)


class EtapeError(ValueError):
    """Étape inconnue."""


def ensure_pipeline_steps(conn: sqlite3.Connection) -> None:
    """Pose les 8 étapes et leurs textes ; ne touche jamais ``enabled``.

    Args:
        conn: Connexion à la base (commit par l'appelant).
    """
    from serge.etape_fiches import FICHES
    from serge.horloge import iso_utc

    now = iso_utc()
    for ident, rang in STEPS:
        fiche = FICHES[ident]
        docs = (
            fiche['titre'],
            fiche['pourquoi'],
            fiche['argent'],
            fiche['dependance'],
            fiche['comment'],
            fiche['doc_md'],
        )
        row = conn.execute(
            'SELECT titre, pourquoi, argent, dependance, comment, doc_md'
            ' FROM pipeline_steps WHERE id=?',
            (ident,),
        ).fetchone()
        if row is None:
            conn.execute(
                'INSERT INTO pipeline_steps(id, enabled, rang, titre,'
                ' pourquoi, argent, dependance, comment, doc_md, files_sha,'
                ' updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (ident, 1, rang, *docs, '', now),
            )
            continue
        conn.execute(
            'UPDATE pipeline_steps SET rang=?, titre=?, pourquoi=?,'
            ' argent=?, dependance=?, comment=?, doc_md=? WHERE id=?',
            (rang, *docs, ident),
        )
        if tuple(str(c or '') for c in row) != docs:
            conn.execute(
                'UPDATE pipeline_steps SET updated_at=? WHERE id=?',
                (now, ident),
            )
    conn.execute(
        'DELETE FROM pipeline_steps WHERE id NOT IN'
        f' ({",".join("?" * len(ETAPE_IDS))})',
        ETAPE_IDS,
    )


def etats_etapes(conn: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    """L'état de chaque étape, dans l'ordre de la chaîne.

    Args:
        conn: Connexion à la base.

    Returns:
        ``{id: {marche, rang}}``.
    """
    ensure_pipeline_steps(conn)
    return {
        str(row[0]): {'marche': bool(row[1]), 'rang': int(row[2])}
        for row in conn.execute(
            'SELECT id, enabled, rang FROM pipeline_steps ORDER BY rang, id'
        ).fetchall()
    }


def etapes_coupees(conn: sqlite3.Connection) -> frozenset[str]:
    """Les étapes coupées (vide si tout est en marche)."""
    return frozenset(
        ident
        for ident, spec in etats_etapes(conn).items()
        if not spec['marche']
    )


def set_etape_marche(
    conn: sqlite3.Connection, ident: str, marche: bool
) -> dict[str, Any]:
    """Coupe ou remet en marche une étape.

    Args:
        conn: Connexion à la base (commit par l'appelant).
        ident: Id d'étape.
        marche: True = ses invocations peuvent tourner.

    Returns:
        ``{id, marche}``.

    Raises:
        EtapeError: Id inconnu.
    """
    if ident not in ETAPE_IDS:
        raise EtapeError(f'étape inconnue : {ident}')
    ensure_pipeline_steps(conn)
    conn.execute(
        'UPDATE pipeline_steps SET enabled=? WHERE id=?',
        (1 if marche else 0, ident),
    )
    return {'id': ident, 'marche': etats_etapes(conn)[ident]['marche']}
