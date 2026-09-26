#!/usr/bin/env python3
"""Étapes du pipe : sacs de vie du projet + interrupteur (etape_id)."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

# Enum fermé (P3). kinds = actions typiques du sac, plus le coupe-circuit.
ETAPE_IDS = (
    'pre_prospection',
    'conception_poc',
    'prospection_light',
    'choix_venture',
    'build_venture',
    'prospection_lourde',
    'collect_feedback',
    'caisse',
)

SEED: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    (
        'pre_prospection',
        0,
        ('listen.collect', 'listen.business_cycle'),
    ),
    ('conception_poc', 1, ()),
    ('prospection_light', 2, ('email.send', 'voice.send')),
    ('choix_venture', 3, ()),
    ('build_venture', 4, ()),
    (
        'prospection_lourde',
        5,
        (
            'inbound.classify',
            'inbound.reply_priority',
            'inbound.judge_other',
            'email.poll',
            'voice.score',
        ),
    ),
    ('collect_feedback', 6, ('memory.consolidate', 'memory.apply')),
    ('caisse', 7, ()),
)

KIND_DEFAUT: dict[str, str] = {
    'listen.collect': 'pre_prospection',
    'listen.business_cycle': 'pre_prospection',
    'email.send': 'prospection_light',
    'voice.send': 'prospection_light',
    'inbound.classify': 'prospection_lourde',
    'inbound.reply_priority': 'prospection_lourde',
    'inbound.judge_other': 'prospection_lourde',
    'email.poll': 'prospection_lourde',
    'voice.score': 'prospection_lourde',
    'memory.consolidate': 'collect_feedback',
    'memory.apply': 'collect_feedback',
}

# enabled v7 → v8 (ET / les deux pour les fusions).
_ANCIEN_ENABLED: dict[str, tuple[str, ...]] = {
    'pre_prospection': ('ecoute',),
    'conception_poc': ('hypothese',),
    'prospection_light': ('test', 'qualif'),
    'choix_venture': (),
    'build_venture': (),
    'prospection_lourde': ('conversation', 'intent'),
    'collect_feedback': (),
    'caisse': ('caisse',),
}


class EtapeError(ValueError):
    """Étape inconnue ou payload invalide."""


def etape_pour_kind(kind: str) -> str:
    """Étape par défaut d’un kind ('' si hors épine)."""
    return KIND_DEFAUT.get(kind, '')


def enabled_depuis_v7(anciens: dict[str, int], ident: str) -> int:
    """Transporte l’interrupteur v7. Nouveau sac → marche.

    Args:
        anciens: ``{id_v7: enabled}``.
        ident: Id v8.

    Returns:
        1 si le sac marche.
    """
    sources = _ANCIEN_ENABLED.get(ident, ())
    if not sources:
        return 1
    return 1 if all(anciens.get(src, 1) for src in sources) else 0


def ensure_pipeline_steps(conn: sqlite3.Connection) -> None:
    """Pose les 8 étapes ; met à jour kinds/docs, jamais ``enabled``.

    Args:
        conn: Canon (commit par l’appelant).
    """
    from serge.etape_fiches import FICHES
    from serge.horloge import iso_utc

    now = iso_utc()
    for ident, rang, kinds in SEED:
        fiche = FICHES[ident]
        blob = json.dumps(list(kinds), ensure_ascii=False)
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
                'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang,'
                ' titre, pourquoi, argent, dependance, comment, doc_md,'
                ' files_sha, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (ident, 1, blob, rang, *docs, '', now),
            )
            continue
        conn.execute(
            'UPDATE pipeline_steps SET kinds_json=?, rang=?, titre=?,'
            ' pourquoi=?, argent=?, dependance=?, comment=?, doc_md=?'
            ' WHERE id=?',
            (blob, rang, *docs, ident),
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
    """État de toutes les étapes (semence si table vide).

    Args:
        conn: Canon (lecture, éventuellement semence).

    Returns:
        ``{id: {marche, kinds, rang}}``.
    """
    ensure_pipeline_steps(conn)
    rows = conn.execute(
        'SELECT id, enabled, kinds_json, rang FROM pipeline_steps'
        ' ORDER BY rang, id'
    ).fetchall()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        kinds = _kinds(row[2])
        out[str(row[0])] = {
            'marche': bool(row[1]),
            'kinds': kinds,
            'rang': int(row[3]),
        }
    return out


def etapes_coupees(conn: sqlite3.Connection) -> frozenset[str]:
    """Ids d’étapes coupées — l’ordonnanceur ignore leurs work items.

    Args:
        conn: Canon.

    Returns:
        Ensemble d’ids (vide si tout est en marche).
    """
    return frozenset(
        ident
        for ident, spec in etats_etapes(conn).items()
        if not spec['marche']
    )


def kinds_coupes(conn: sqlite3.Connection) -> frozenset[str]:
    """Kinds typiques des étapes coupées (doc / repli, pas le coupe-circuit).

    Args:
        conn: Canon.

    Returns:
        Ensemble de kinds des sacs coupés.
    """
    blocked: set[str] = set()
    for spec in etats_etapes(conn).values():
        if not spec['marche']:
            blocked.update(spec['kinds'])
    return frozenset(blocked)


def set_etape_marche(
    conn: sqlite3.Connection, ident: str, marche: bool
) -> dict[str, Any]:
    """Coupe ou remet en marche une étape.

    Args:
        conn: Canon (commit par l’appelant).
        ident: Id d’étape.
        marche: True = l’ordonnanceur accepte les work items du sac.

    Returns:
        ``{id, marche, kinds}``.

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
    spec = etats_etapes(conn)[ident]
    return {'id': ident, 'marche': spec['marche'], 'kinds': spec['kinds']}


def _kinds(raw: object) -> list[str]:
    if isinstance(raw, list):
        data = raw
    else:
        try:
            data = json.loads(str(raw or '[]'))
        except (TypeError, ValueError):
            return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data if item]
