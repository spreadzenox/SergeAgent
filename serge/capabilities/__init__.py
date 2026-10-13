#!/usr/bin/env python3
"""Les capacités : ce que le code sait faire, déclaré en base au démarrage.

Une capacité est un savoir-faire général, réglé par des paramètres lus en
base. Elle ne connaît jamais une invocation, une étape ou un business en
particulier. C'est la seule table que le code remplit lui-même : une
capacité retirée du code reste en base, marquée absente
(``available`` = 0), pour que Mission Control signale ce qui s'en servait.
Chaque famille de capacités est déclarée dans son fichier de ce dossier.
"""

from __future__ import annotations

import sqlite3

from serge.capabilities.base import BASE
from serge.capabilities.chantier import CHANTIER
from serge.capabilities.conversations import CONVERSATIONS
from serge.capabilities.model import Capability

CAPABILITIES: tuple[Capability, ...] = (*BASE, *CONVERSATIONS, *CHANTIER)


def ensure_capabilities(conn: sqlite3.Connection) -> None:
    """Déclare en base les capacités du code, sans jamais en effacer.

    Le titre, la description, le chemin et les paramètres suivent le code ;
    une capacité absente du code est marquée ``available`` = 0.

    Args:
        conn: Canon (commit par l'appelant).
    """
    from serge.horloge import iso_utc

    now = iso_utc()
    known = {cap.id for cap in CAPABILITIES}
    for cap in CAPABILITIES:
        conn.execute(
            'INSERT INTO capabilities(id, title, doc_md, available, code_path,'
            ' acts_outside, updated_at) VALUES(?,?,?,1,?,?,?)'
            ' ON CONFLICT(id) DO UPDATE SET title=excluded.title,'
            ' doc_md=excluded.doc_md, available=1,'
            ' code_path=excluded.code_path,'
            ' acts_outside=excluded.acts_outside',
            (
                cap.id,
                cap.title,
                cap.doc_md,
                cap.code_path,
                int(cap.acts_outside),
                now,
            ),
        )
        conn.execute(
            'DELETE FROM capability_params WHERE capability_id=?', (cap.id,)
        )
        for position, param in enumerate(cap.params):
            conn.execute(
                'INSERT INTO capability_params(capability_id, name, type,'
                ' required, description, position) VALUES(?,?,?,?,?,?)',
                (
                    cap.id,
                    param.name,
                    param.type,
                    int(param.required),
                    param.description,
                    position,
                ),
            )
    for (ident,) in conn.execute('SELECT id FROM capabilities').fetchall():
        if str(ident) not in known:
            conn.execute(
                'UPDATE capabilities SET available=0 WHERE id=?', (ident,)
            )
