#!/usr/bin/env python3
"""Les administrateurs Discord de Serge (décision Q86).

Chaque administrateur reçoit chaque ticket en message privé, et n'importe
lequel peut y répondre : la première réponse tranche le ticket pour tous.
On les ajoute dans Mission Control par leur identifiant Discord (mode
développeur de Discord, « Copier l'identifiant »). Pour que le bot puisse
lui écrire, la personne doit être sur le serveur Discord de Serge.
"""

from __future__ import annotations

import re
import sqlite3
from typing import Any

from serge.db.store import append_event, utcnow

# Un identifiant Discord : un nombre de 17 à 20 chiffres.
_SNOWFLAKE = re.compile(r'\d{17,20}')
# Le drapeau posé quand l'administrateur du fichier d'instance a été repris.
FLAG_REPRIS = 'discord.admins_initialises'


def admins(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Les administrateurs, dans l'ordre où ils ont été ajoutés."""
    return [
        {
            'user_id': str(r[0]),
            'name': str(r[1]),
            'added_by': str(r[2]),
            'added_at': str(r[3]),
        }
        for r in conn.execute(
            'SELECT user_id, name, added_by, added_at FROM discord_admins'
            ' ORDER BY added_at, user_id'
        ).fetchall()
    ]


def admin_name(conn: sqlite3.Connection, user_id: str) -> str:
    """Le nom d'un administrateur, ``''`` s'il n'en est pas un."""
    row = conn.execute(
        'SELECT name, user_id FROM discord_admins WHERE user_id=?',
        (user_id,),
    ).fetchone()
    return str(row[0] or row[1]) if row else ''


def is_admin(conn: sqlite3.Connection, user_id: str) -> bool:
    """Vrai si ce compte Discord est un administrateur de Serge."""
    return bool(admin_name(conn, user_id))


def add_admin(
    conn: sqlite3.Connection, user_id: str, name: str, by: str
) -> str:
    """Ajoute un administrateur ; rend ce qui ne va pas, ou ``''``.

    Il reçoit les tickets ouverts après son ajout ; les plus anciens restent
    dans Mission Control (page Décisions).
    """
    user_id = user_id.strip()
    if not _SNOWFLAKE.fullmatch(user_id):
        return (
            'identifiant Discord : un nombre de 17 à 20 chiffres (clic droit'
            ' sur la personne, « Copier l’identifiant », en mode développeur)'
        )
    if is_admin(conn, user_id):
        return 'déjà administrateur'
    conn.execute(
        'INSERT INTO discord_admins(user_id, name, added_by, added_at)'
        ' VALUES(?,?,?,?)',
        (user_id, name.strip(), by, utcnow()),
    )
    append_event(
        conn,
        actor=by,
        type='discord.admin_added',
        payload={'user_id': user_id, 'name': name.strip()},
    )
    return ''


def remove_admin(conn: sqlite3.Connection, user_id: str, by: str) -> str:
    """Retire un administrateur ; rend ce qui ne va pas, ou ``''``.

    Il ne reçoit plus de ticket ; ses anciens messages restent chez lui.
    """
    if not is_admin(conn, user_id):
        return 'pas administrateur'
    conn.execute('DELETE FROM discord_admins WHERE user_id=?', (user_id,))
    conn.execute(
        "DELETE FROM ticket_messages WHERE user_id=? AND message_id=''",
        (user_id,),
    )
    append_event(
        conn,
        actor=by,
        type='discord.admin_removed',
        payload={'user_id': user_id},
    )
    return ''


def reprendre_admin_instance(
    conn: sqlite3.Connection, owner_user_id: str
) -> None:
    """Reprend une fois l'administrateur du fichier d'instance.

    Avant le lot 8 bis, un seul administrateur était déclaré dans le
    fichier d'instance (``owner_user_id``). Il devient le premier
    administrateur en base, une seule fois : retiré ensuite dans Mission
    Control, il ne revient pas.
    """
    if conn.execute(
        'SELECT 1 FROM runtime_flags WHERE name=?', (FLAG_REPRIS,)
    ).fetchone():
        return
    if _SNOWFLAKE.fullmatch(owner_user_id.strip()) and not is_admin(
        conn, owner_user_id.strip()
    ):
        add_admin(
            conn,
            owner_user_id,
            'Administrateur du fichier d’instance',
            'discord',
        )
    conn.execute(
        'INSERT OR REPLACE INTO runtime_flags(name, value, set_by, set_at)'
        " VALUES(?, 'oui', 'discord', ?)",
        (FLAG_REPRIS, utcnow()),
    )
