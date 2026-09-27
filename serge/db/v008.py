#!/usr/bin/env python3
"""Migration v8 : etape_id sur les work items + 8 sacs de vie du projet."""

from __future__ import annotations

import json
import sqlite3

# Les valeurs de l'époque, recopiées ici : une migration ne dépend pas du
# code qui a changé depuis (les « kinds » ont disparu au lot 6).
SEED: tuple[tuple[str, int, tuple[str, ...]], ...] = (
    ('pre_prospection', 0, ('listen.collect', 'listen.business_cycle')),
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
    kind: ident for ident, _rang, kinds in SEED for kind in kinds
}
# enabled v7 → v8 (ET logique pour les fusions).
_ANCIEN_ENABLED: dict[str, tuple[str, ...]] = {
    'pre_prospection': ('ecoute',),
    'conception_poc': ('hypothese',),
    'prospection_light': ('test', 'qualif'),
    'prospection_lourde': ('conversation', 'intent'),
    'caisse': ('caisse',),
}


def enabled_depuis_v7(anciens: dict[str, int], ident: str) -> int:
    """Transporte l’interrupteur v7. Nouveau sac → marche."""
    sources = _ANCIEN_ENABLED.get(ident, ())
    if not sources:
        return 1
    return 1 if all(anciens.get(src, 1) for src in sources) else 0


def apply_v008(connection: sqlite3.Connection) -> None:
    """Ajoute ``work_items.etape_id``, remappe les étapes.

    Args:
        connection: Connexion (commit par l’appelant).
    """
    cols = {
        str(row[1])
        for row in connection.execute('PRAGMA table_info(work_items)')
    }
    if 'etape_id' not in cols:
        connection.execute(
            'ALTER TABLE work_items ADD COLUMN etape_id'
            " TEXT NOT NULL DEFAULT ''"
        )
    for kind, etape in KIND_DEFAUT.items():
        connection.execute(
            "UPDATE work_items SET etape_id=? WHERE etape_id='' AND kind=?",
            (etape, kind),
        )
    anciens = {
        str(row[0]): int(row[1])
        for row in connection.execute('SELECT id, enabled FROM pipeline_steps')
    }
    connection.execute('DELETE FROM pipeline_steps')
    for ident, rang, kinds in SEED:
        connection.execute(
            'INSERT INTO pipeline_steps(id, enabled, kinds_json, rang)'
            ' VALUES(?,?,?,?)',
            (
                ident,
                enabled_depuis_v7(anciens, ident),
                json.dumps(list(kinds), ensure_ascii=False),
                rang,
            ),
        )
