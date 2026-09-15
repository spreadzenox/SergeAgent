#!/usr/bin/env python3
"""Applique les migrations canon dans l’ordre. Ne sème pas le catalogue."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence

from serge.db.schema import SCHEMA_VERSION, apply_v007
from serge.db.v008 import apply_v008
from serge.db.v009 import apply_v009
from serge.db.v010 import apply_v010
from serge.db.v011 import apply_v011
from serge.db.v012 import apply_v012

ApplyFn = Callable[[sqlite3.Connection], None]
Migration = tuple[int, ApplyFn]

MIGRATIONS: tuple[Migration, ...] = (
    (7, apply_v007),
    (8, apply_v008),
    (9, apply_v009),
    (10, apply_v010),
    (11, apply_v011),
    (12, apply_v012),
)


class MigrateError(ValueError):
    """Canon plus récent que le code, ou trou dans la chaîne."""


def read_version(connection: sqlite3.Connection) -> int:
    """Version tamponnée, ou 0 si la table n’existe pas encore.

    Args:
        connection: Connexion SQLite.

    Returns:
        Entier ≥ 0.
    """
    try:
        row = connection.execute(
            'SELECT MAX(version) FROM schema_version'
        ).fetchone()
    except sqlite3.OperationalError:
        return 0
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def stamp(connection: sqlite3.Connection, version: int) -> None:
    """Écrit la tête du schéma (une ligne).

    Args:
        connection: Connexion (commit par l’appelant).
        version: Version appliquée.
    """
    connection.execute('DELETE FROM schema_version')
    connection.execute(
        'INSERT INTO schema_version(version, applied_at)'
        " VALUES(?, datetime('now'))",
        (version,),
    )


def apply_pending(
    connection: sqlite3.Connection,
    migrations: Sequence[Migration] | None = None,
    head: int | None = None,
) -> int:
    """Enchaîne les migrations manquantes, puis s’arrête.

    Une base vide (version 0) absorbe la première migration même si
    son numéro n’est pas 1 (socle v7). Ensuite : strictement +1.

    Args:
        connection: Connexion (commit par l’appelant).
        migrations: Chaîne (défaut : ``MIGRATIONS``).
        head: Version du code (défaut : ``SCHEMA_VERSION``).

    Returns:
        Version atteinte.

    Raises:
        MigrateError: DB plus récente que le code, ou trou après le socle.
    """
    chain = tuple(migrations) if migrations is not None else MIGRATIONS
    target = SCHEMA_VERSION if head is None else head
    have = read_version(connection)
    if have > target:
        raise MigrateError(f'canon v{have} plus récent que le code v{target}')
    if chain and chain[-1][0] != target:
        raise MigrateError(
            f'tête des migrations {chain[-1][0]} ≠ code v{target}'
        )
    for version, apply in chain:
        if version <= have:
            continue
        if have != 0 and version != have + 1:
            raise MigrateError(f'trou de migration : {have} → {version}')
        apply(connection)
        stamp(connection, version)
        have = version
    return have
