#!/usr/bin/env python3
"""Les protections de l'écriture, toutes réglées en base.

1. Le catalogue (``writable_tables``, ``writable_columns``) : une table ou
   une colonne absente ne peut jamais être écrite par une invocation.
2. Les changements de statut permis (``status_transitions``) : dès qu'une
   colonne a des lignes ici, seuls ces changements passent. Exemple :
   ``CANDIDATE`` → ``POC_SELECTED`` est permis ; comme rien ne permet
   ``SMOKE_RUNNING`` → ``POC_SELECTED``, un business déjà en test est
   refusé.
3. Les doublons (``dedup_rules``) : ``exact`` compare les textes sans
   majuscules, accents ni espaces en trop ; ``shared_words`` compare la
   part de mots en commun, par exemple 72 %.
"""

from __future__ import annotations

import re
import sqlite3
import unicodedata
from collections.abc import Mapping
from typing import Any


class WriteConfigError(ValueError):
    """La règle d'écriture vise une table ou une colonne interdite."""


_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def safe_name(name: str) -> str:
    """Un nom de table ou de colonne, refusé s'il n'est pas un simple nom.

    Raises:
        WriteConfigError: Nom invalide.
    """
    if not _IDENT.match(name):
        raise WriteConfigError(f'nom invalide : {name!r}')
    return name


def check_catalogue(
    conn: sqlite3.Connection, table: str, operation: str, columns: list[str]
) -> None:
    """Refuse une écriture hors du catalogue.

    Raises:
        WriteConfigError: Table, opération ou colonne non autorisée.
    """
    row = conn.execute(
        'SELECT can_insert, can_update FROM writable_tables WHERE table_name=?',
        (table,),
    ).fetchone()
    if row is None:
        raise WriteConfigError(f'table non inscriptible : {table}')
    allowed = row[0] if operation == 'insert' else row[1]
    if not allowed:
        raise WriteConfigError(f'{operation} interdit sur {table}')
    permitted = {
        str(r[0])
        for r in conn.execute(
            'SELECT column_name FROM writable_columns WHERE table_name=?',
            (table,),
        ).fetchall()
    }
    for column in columns:
        if column not in permitted:
            raise WriteConfigError(
                f'colonne non inscriptible : {table}.{column}'
            )


def transition_refusal(
    conn: sqlite3.Connection,
    table: str,
    values: Mapping[str, Any],
    current: Mapping[str, Any] | None,
) -> str:
    """La raison du refus d'un changement de statut, ou ``''``.

    ``current`` vaut ``None`` pour une ligne nouvelle : la valeur de départ
    est alors vide.
    """
    for column, value in values.items():
        rules = conn.execute(
            'SELECT from_value, to_value FROM status_transitions'
            ' WHERE table_name=? AND column_name=?',
            (table, column),
        ).fetchall()
        if not rules:
            continue
        before = '' if current is None else str(current.get(column) or '')
        after = str(value)
        if current is not None and before == after:
            continue
        if (before, after) not in {(str(a), str(b)) for a, b in rules}:
            shown = before or '(création)'
            return (
                f'{table}.{column} : passage de {shown} à {after} non permis'
            )
    return ''


def _normal(text: str) -> str:
    folded = unicodedata.normalize('NFKD', text.casefold())
    bare = ''.join(ch for ch in folded if not unicodedata.combining(ch))
    return ' '.join(bare.split())


def find_duplicate(
    conn: sqlite3.Connection, table: str, values: Mapping[str, Any]
) -> tuple[str, str, str] | None:
    """Une ligne existante trop proche : ``(règle, clé, action)``, ou ``None``.

    La clé est l'``id`` de la ligne existante (ou son ``rowid``).
    """
    for rule_id, method, threshold, action in conn.execute(
        'SELECT id, method, threshold, on_duplicate FROM dedup_rules'
        ' WHERE table_name=? ORDER BY id',
        (table,),
    ).fetchall():
        columns = [
            str(r[0])
            for r in conn.execute(
                'SELECT column_name FROM dedup_rule_columns WHERE rule_id=?'
                ' ORDER BY column_name',
                (rule_id,),
            ).fetchall()
        ]
        if not columns:
            continue
        safe_name(table)
        for column in columns:
            safe_name(column)
        wanted = _normal(' '.join(str(values.get(c) or '') for c in columns))
        if not wanted:
            continue
        key = 'id' if _has_column(conn, table, 'id') else 'rowid'
        select = ', '.join(f'"{c}"' for c in columns)
        for row in conn.execute(
            f'SELECT {key}, {select} FROM "{table}"'
        ).fetchall():
            existing = _normal(' '.join(str(v or '') for v in row[1:]))
            if method == 'exact':
                same = existing == wanted
            else:
                a, b = set(wanted.split()), set(existing.split())
                same = bool(a | b) and len(a & b) * 100 >= threshold * len(
                    a | b
                )
            if same:
                return str(rule_id), str(row[0]), str(action)
    return None


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return column in table_columns(conn, table)


def table_columns(conn: sqlite3.Connection, table: str) -> dict[str, dict]:
    """Les colonnes réelles d'une table : type, obligatoire, clé."""
    return {
        str(r[1]): {
            'type': str(r[2]).upper(),
            'notnull': bool(r[3]),
            'default': r[4],
            'pk': bool(r[5]),
        }
        for r in conn.execute(f'PRAGMA table_info("{safe_name(table)}")')
    }
